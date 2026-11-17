"""Automated read-only ad, social (IG/FB), analytics, and revenue platform sync connector.

Pulls telemetry directly from Google Ads, Meta Ads + Instagram/Facebook Insights,
LinkedIn Ads, TikTok Ads, GA4, Google Search Console, Stripe, and Shopify using
pure Python stdlib HTTPS requests, writes normalized snapshots to data/exports/,
unifies customer cohorts in SQLite (IdentityResolver), and builds the Orchestrator
state payload for scripts/next_action.py.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from calculators import to_float
from connectors.csv_normalizer import neutralize_csv_cell
from connectors.identity_resolver import IdentityResolver, anonymize_customer_key
from scripts.geo_benchmark import validate_endpoint_url


SUPPORTED_PLATFORMS = (
    "google_ads",
    "meta_ads",
    "linkedin_ads",
    "tiktok_ads",
    "ga4",
    "gsc",
    "stripe",
    "shopify",
)

TransportFn = Callable[[urllib.request.Request], dict[str, Any]]


def _default_transport(req: urllib.request.Request) -> dict[str, Any]:
    validate_endpoint_url(req.full_url)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        # Never echo request headers/tokens in error output
        raise RuntimeError(f"Platform API HTTP {exc.code} on {urllib.parse.urlparse(req.full_url).hostname}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Platform API network error: {exc.reason}") from None


def refresh_google_oauth_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    transport: TransportFn | None = None,
) -> str:
    """Exchange a Google OAuth2 refresh token for a short-lived access token."""
    tx = transport or _default_transport
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    resp = tx(req)
    token = str(resp.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Google OAuth token refresh returned no access_token")
    return token


def _resolve_google_token(prefix: str, env: dict[str, str], transport: TransportFn | None) -> str | None:
    direct = (env.get(f"{prefix}_ACCESS_TOKEN") or env.get("GOOGLE_OAUTH_ACCESS_TOKEN") or "").strip()
    if direct:
        return direct
    cid = (env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    csec = (env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    rtok = (env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
    if cid and csec and rtok:
        return refresh_google_oauth_token(cid, csec, rtok, transport=transport)
    return None


def detect_configured_platforms(env: dict[str, str] | None = None) -> list[str]:
    """Return list of platforms that have required read-only credentials present in env."""
    e = env if env is not None else dict(os.environ)
    has_google_oauth = bool(
        e.get("GOOGLE_OAUTH_ACCESS_TOKEN")
        or (e.get("GOOGLE_OAUTH_CLIENT_ID") and e.get("GOOGLE_OAUTH_CLIENT_SECRET") and e.get("GOOGLE_OAUTH_REFRESH_TOKEN"))
    )
    configured: list[str] = []
    if e.get("GOOGLE_ADS_CUSTOMER_ID") and e.get("GOOGLE_ADS_DEVELOPER_TOKEN") and (e.get("GOOGLE_ADS_ACCESS_TOKEN") or has_google_oauth):
        configured.append("google_ads")
    if e.get("META_ACCESS_TOKEN") and (e.get("META_AD_ACCOUNT_ID") or e.get("IG_BUSINESS_ACCOUNT_ID") or e.get("FB_PAGE_ID")):
        configured.append("meta_ads")
    if e.get("LINKEDIN_ACCESS_TOKEN") and e.get("LINKEDIN_AD_ACCOUNT_ID"):
        configured.append("linkedin_ads")
    if e.get("TIKTOK_ACCESS_TOKEN") and e.get("TIKTOK_ADVERTISER_ID"):
        configured.append("tiktok_ads")
    if e.get("GA4_PROPERTY_ID") and (e.get("GA4_ACCESS_TOKEN") or has_google_oauth):
        configured.append("ga4")
    if e.get("GSC_SITE_URL") and (e.get("GSC_ACCESS_TOKEN") or has_google_oauth):
        configured.append("gsc")
    if e.get("STRIPE_RESTRICTED_KEY"):
        configured.append("stripe")
    if e.get("SHOPIFY_STORE_DOMAIN") and e.get("SHOPIFY_ADMIN_TOKEN"):
        configured.append("shopify")
    return configured


def _write_normalized_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean_row = {
                k: neutralize_csv_cell(str(row.get(k, ""))) if isinstance(row.get(k), str) else row.get(k, "")
                for k in fieldnames
            }
            writer.writerow(clean_row)
    return str(path)


def fetch_google_ads(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch campaign and search-term performance from Google Ads REST searchStream API."""
    tx = transport or _default_transport
    token = _resolve_google_token("GOOGLE_ADS", env, tx)
    dev_token = (env.get("GOOGLE_ADS_DEVELOPER_TOKEN") or "").strip()
    customer_id = (env.get("GOOGLE_ADS_CUSTOMER_ID") or "").replace("-", "").strip()
    if not (token and dev_token and customer_id):
        raise ValueError("Missing GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_DEVELOPER_TOKEN, or OAuth token")

    url = f"https://googleads.googleapis.com/v18/customers/{customer_id}/googleAds:searchStream"
    gaql = (
        "SELECT campaign.id, campaign.name, metrics.cost_micros, metrics.impressions, "
        "metrics.clicks, metrics.conversions, metrics.conversions_value, "
        "search_term_view.search_term "
        f"FROM search_term_view WHERE segments.date DURING LAST_{int(lookback_days)}_DAYS"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "developer-token": dev_token,
        "Content-Type": "application/json",
    }
    login_cid = (env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or "").replace("-", "").strip()
    if login_cid:
        headers["login-customer-id"] = login_cid

    req = urllib.request.Request(url, data=json.dumps({"query": gaql}).encode("utf-8"), headers=headers, method="POST")
    payload = tx(req)
    batches = payload if isinstance(payload, list) else payload.get("batches", [payload])

    rows: list[dict[str, Any]] = []
    campaigns_map: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch.get("results", []):
            camp = item.get("campaign", {})
            met = item.get("metrics", {})
            stv = item.get("searchTermView", {})
            cid = str(camp.get("id") or "gads-unknown")
            cname = str(camp.get("name") or cid)
            spend = round(float(met.get("costMicros", 0)) / 1_000_000.0, 2)
            impr = int(met.get("impressions", 0))
            clicks = int(met.get("clicks", 0))
            convs = round(float(met.get("conversions", 0.0)), 2)
            rev = round(float(met.get("conversionsValue", 0.0)), 2)
            term = str(stv.get("searchTerm") or "").strip()
            rows.append(
                {
                    "platform": "google_ads",
                    "campaign_id": f"gads-{cid}",
                    "campaign_name": cname,
                    "search_term": term,
                    "spend_usd": spend,
                    "impressions": impr,
                    "clicks": clicks,
                    "conversions": convs,
                    "revenue_usd": rev,
                }
            )
            agg = campaigns_map.setdefault(
                f"gads-{cid}",
                {
                    "campaign_id": f"gads-{cid}",
                    "campaign_name": cname,
                    "channel": "paid_search",
                    "spend": 0.0,
                    "revenue": 0.0,
                    "conversions": 0.0,
                    "days": lookback_days,
                    "days_running": lookback_days,
                },
            )
            agg["spend"] = round(agg["spend"] + spend, 2)
            agg["revenue"] = round(agg["revenue"] + rev, 2)
            agg["conversions"] = round(agg["conversions"] + convs, 2)

    active_campaigns = []
    for c in campaigns_map.values():
        c["roas"] = round(c["revenue"] / c["spend"], 2) if c["spend"] > 0 else 0.0
        active_campaigns.append(c)

    return {"rows": rows, "active_campaigns": active_campaigns}


def fetch_meta_ads_and_social(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch Meta Ads (FB + IG placements) and organic Instagram/Facebook post engagement."""
    tx = transport or _default_transport
    token = (env.get("META_ACCESS_TOKEN") or "").strip()
    if not token:
        raise ValueError("Missing META_ACCESS_TOKEN")

    ad_account_id = (env.get("META_AD_ACCOUNT_ID") or "").removeprefix("act_").strip()
    ig_id = (env.get("IG_BUSINESS_ACCOUNT_ID") or "").strip()
    fb_page_id = (env.get("FB_PAGE_ID") or "").strip()

    ad_rows: list[dict[str, Any]] = []
    active_campaigns: list[dict[str, Any]] = []

    if ad_account_id:
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        until = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        qs = urllib.parse.urlencode(
            {
                "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions,action_values,publisher_platform",
                "time_range": json.dumps({"since": since, "until": until}),
                "level": "campaign",
            }
        )
        url = f"https://graph.facebook.com/v21.0/act_{ad_account_id}/insights?{qs}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        resp = tx(req)
        for item in resp.get("data", []):
            spend = round(float(item.get("spend", 0.0)), 2)
            impr = int(item.get("impressions", 0))
            clicks = int(item.get("clicks", 0))
            convs = 0.0
            for act in item.get("actions", []) or []:
                if act.get("action_type") in ("purchase", "lead", "offsite_conversion.fb_pixel_purchase"):
                    convs += float(act.get("value", 0.0))
            rev = 0.0
            for av in item.get("action_values", []) or []:
                if av.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
                    rev += float(av.get("value", 0.0))
            cid = f"meta-{item.get('campaign_id', 'unknown')}"
            cname = str(item.get("campaign_name") or cid)
            pub = str(item.get("publisher_platform") or "facebook_instagram")
            ad_rows.append(
                {
                    "platform": f"meta_{pub}",
                    "campaign_id": cid,
                    "campaign_name": cname,
                    "publisher_platform": pub,
                    "spend_usd": spend,
                    "impressions": impr,
                    "clicks": clicks,
                    "conversions": round(convs, 2),
                    "revenue_usd": round(rev, 2),
                }
            )
            active_campaigns.append(
                {
                    "campaign_id": cid,
                    "campaign_name": cname,
                    "channel": "paid_social",
                    "spend": spend,
                    "revenue": round(rev, 2),
                    "conversions": round(convs, 2),
                    "roas": round(rev / spend, 2) if spend > 0 else 0.0,
                    "days": lookback_days,
                    "days_running": lookback_days,
                }
            )

    organic_posts: list[dict[str, Any]] = []
    raw_social: list[dict[str, Any]] = []

    if ig_id:
        ig_url = (
            f"https://graph.facebook.com/v21.0/{ig_id}/media?"
            + urllib.parse.urlencode(
                {"fields": "id,caption,media_type,like_count,comments_count,saved,plays,reach,permalink"}
            )
        )
        ig_resp = tx(urllib.request.Request(ig_url, headers={"Authorization": f"Bearer {token}"}, method="GET"))
        for m in ig_resp.get("data", []):
            score = float(m.get("saved", 0) or 0) * 3.0 + float(m.get("plays", 0) or m.get("reach", 0) or 0) * 0.05
            raw_social.append(
                {
                    "post_id": f"ig-{m.get('id')}",
                    "network": "instagram",
                    "media_type": str(m.get("media_type") or "REELS"),
                    "caption": str(m.get("caption") or "")[:140],
                    "reach": int(m.get("reach", 0) or 0),
                    "saves": int(m.get("saved", 0) or 0),
                    "engagement_score": round(score, 2),
                    "permalink": str(m.get("permalink") or ""),
                }
            )

    if fb_page_id:
        fb_url = (
            f"https://graph.facebook.com/v21.0/{fb_page_id}/posts?"
            + urllib.parse.urlencode({"fields": "id,message,shares,permalink_url"})
        )
        fb_resp = tx(urllib.request.Request(fb_url, headers={"Authorization": f"Bearer {token}"}, method="GET"))
        for p in fb_resp.get("data", []):
            shares_cnt = int((p.get("shares") or {}).get("count", 0))
            score = float(shares_cnt) * 4.0 + 10.0
            raw_social.append(
                {
                    "post_id": f"fb-{p.get('id')}",
                    "network": "facebook",
                    "media_type": "FEED_OR_REEL",
                    "caption": str(p.get("message") or "")[:140],
                    "reach": shares_cnt * 50,
                    "saves": shares_cnt,
                    "engagement_score": round(score, 2),
                    "permalink": str(p.get("permalink_url") or ""),
                }
            )

    if raw_social:
        scores = [x["engagement_score"] for x in raw_social if x["engagement_score"] > 0]
        median_score = statistics.median(scores) if scores else 1.0
        for item in raw_social:
            mult = round(item["engagement_score"] / max(median_score, 0.01), 2)
            item["save_or_watch_multiplier"] = mult
            item["receipt"] = "data/exports/social_organic_ig_fb.csv"
            organic_posts.append(item)

    return {
        "rows": ad_rows,
        "active_campaigns": active_campaigns,
        "organic_social_posts": organic_posts,
    }


def fetch_linkedin_ads(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch LinkedIn Campaign Manager ad analytics."""
    tx = transport or _default_transport
    token = (env.get("LINKEDIN_ACCESS_TOKEN") or "").strip()
    account_id = (env.get("LINKEDIN_AD_ACCOUNT_ID") or "").strip()
    if not (token and account_id):
        raise ValueError("Missing LINKEDIN_ACCESS_TOKEN or LINKEDIN_AD_ACCOUNT_ID")

    url = (
        "https://api.linkedin.com/rest/adAnalytics?"
        + urllib.parse.urlencode(
            {
                "q": "analytics",
                "pivot": "CAMPAIGN",
                "accounts": f"urn:li:sponsoredAccount:{account_id}",
            }
        )
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": "202410",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        method="GET",
    )
    resp = tx(req)
    rows: list[dict[str, Any]] = []
    active_campaigns: list[dict[str, Any]] = []
    for idx, el in enumerate(resp.get("elements", []), start=1):
        cid = f"li-{el.get('pivotValue', idx)}"
        spend = round(float(el.get("costInUsd", 0.0)), 2)
        impr = int(el.get("impressions", 0))
        clicks = int(el.get("clicks", 0))
        convs = round(float(el.get("externalWebsiteConversions", 0.0)), 2)
        rev = round(float(el.get("conversionValueInLocalCurrency", 0.0)), 2)
        rows.append(
            {
                "platform": "linkedin_ads",
                "campaign_id": cid,
                "campaign_name": str(el.get("campaignName") or cid),
                "spend_usd": spend,
                "impressions": impr,
                "clicks": clicks,
                "conversions": convs,
                "revenue_usd": rev,
            }
        )
        active_campaigns.append(
            {
                "campaign_id": cid,
                "campaign_name": str(el.get("campaignName") or cid),
                "channel": "paid_social",
                "spend": spend,
                "revenue": rev,
                "conversions": convs,
                "roas": round(rev / spend, 2) if spend > 0 else 0.0,
                "days": lookback_days,
                "days_running": lookback_days,
            }
        )
    return {"rows": rows, "active_campaigns": active_campaigns}


def fetch_tiktok_ads(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch TikTok Ads integrated campaign report."""
    tx = transport or _default_transport
    token = (env.get("TIKTOK_ACCESS_TOKEN") or "").strip()
    adv_id = (env.get("TIKTOK_ADVERTISER_ID") or "").strip()
    if not (token and adv_id):
        raise ValueError("Missing TIKTOK_ACCESS_TOKEN or TIKTOK_ADVERTISER_ID")

    url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/?" + urllib.parse.urlencode(
        {"advertiser_id": adv_id, "report_type": "BASIC", "data_level": "AUCTION_CAMPAIGN"}
    )
    req = urllib.request.Request(url, headers={"Access-Token": token}, method="GET")
    resp = tx(req)
    rows: list[dict[str, Any]] = []
    active_campaigns: list[dict[str, Any]] = []
    for item in ((resp.get("data") or {}).get("list") or []):
        dims = item.get("dimensions", {})
        met = item.get("metrics", {})
        cid = f"tt-{dims.get('campaign_id', 'unknown')}"
        spend = round(float(met.get("spend", 0.0)), 2)
        impr = int(met.get("impressions", 0))
        clicks = int(met.get("clicks", 0))
        convs = round(float(met.get("conversion", 0.0)), 2)
        rev = round(float(met.get("total_complete_payment_rate", 0.0)), 2)
        rows.append(
            {
                "platform": "tiktok_ads",
                "campaign_id": cid,
                "campaign_name": str(met.get("campaign_name") or cid),
                "spend_usd": spend,
                "impressions": impr,
                "clicks": clicks,
                "conversions": convs,
                "revenue_usd": rev,
            }
        )
        active_campaigns.append(
            {
                "campaign_id": cid,
                "campaign_name": str(met.get("campaign_name") or cid),
                "channel": "paid_social",
                "spend": spend,
                "revenue": rev,
                "conversions": convs,
                "roas": round(rev / spend, 2) if spend > 0 else 0.0,
                "days": lookback_days,
                "days_running": lookback_days,
            }
        )
    return {"rows": rows, "active_campaigns": active_campaigns}


def fetch_ga4(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch GA4 channel acquisition & conversion health via Google Analytics Data API."""
    tx = transport or _default_transport
    token = _resolve_google_token("GA4", env, tx)
    prop_id = (env.get("GA4_PROPERTY_ID") or "").removeprefix("properties/").strip()
    if not (token and prop_id):
        raise ValueError("Missing GA4_PROPERTY_ID or OAuth token")

    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{prop_id}:runReport"
    body = {
        "dateRanges": [{"startDate": f"{int(lookback_days)}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
        "metrics": [{"name": "sessions"}, {"name": "conversions"}, {"name": "totalRevenue"}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    resp = tx(req)
    rows: list[dict[str, Any]] = []
    total_convs = 0.0
    for r in resp.get("rows", []):
        dims = r.get("dimensionValues", [{}])
        mets = r.get("metricValues", [{}, {}, {}])
        ch = str(dims[0].get("value") or "Unassigned")
        sess = int(float(mets[0].get("value", 0) or 0))
        convs = round(float(mets[1].get("value", 0.0) or 0.0), 2)
        rev = round(float(mets[2].get("value", 0.0) or 0.0), 2)
        total_convs += convs
        rows.append(
            {
                "channel_group": ch,
                "sessions": sess,
                "conversions": convs,
                "revenue_usd": rev,
            }
        )
    return {
        "rows": rows,
        "tracking_verified": total_convs > 0,
        "monthly_conversions": int(round(total_convs)),
    }


def fetch_gsc(
    env: dict[str, str],
    lookback_days: int = 30,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch Search Console query positions, clicks, and impressions."""
    tx = transport or _default_transport
    token = _resolve_google_token("GSC", env, tx)
    site_url = (env.get("GSC_SITE_URL") or "").strip()
    if not (token and site_url):
        raise ValueError("Missing GSC_SITE_URL or OAuth token")

    encoded_site = urllib.parse.quote(site_url, safe="")
    url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"
    start_dt = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = {"startDate": start_dt, "endDate": end_dt, "dimensions": ["query"], "rowLimit": 250}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    resp = tx(req)
    rows: list[dict[str, Any]] = []
    for r in resp.get("rows", []):
        keys = r.get("keys") or [""]
        rows.append(
            {
                "search_term": str(keys[0]).strip(),
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr": round(float(r.get("ctr", 0.0)), 4),
                "avg_position": round(float(r.get("position", 99.0)), 2),
            }
        )
    return {"rows": rows}


def fetch_stripe_revenue(
    env: dict[str, str],
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch succeeded charges from Stripe API with immediate SHA-256 PII anonymization."""
    tx = transport or _default_transport
    key = (env.get("STRIPE_RESTRICTED_KEY") or "").strip()
    if not key:
        raise ValueError("Missing STRIPE_RESTRICTED_KEY")

    url = "https://api.stripe.com/v1/charges?limit=100"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"}, method="GET")
    resp = tx(req)

    by_customer: dict[str, dict[str, Any]] = {}
    for ch in resp.get("data", []):
        if not ch.get("paid") or ch.get("refunded"):
            continue
        raw_id = str(
            (ch.get("billing_details") or {}).get("email")
            or ch.get("customer")
            or ch.get("id")
        )
        anon_id = anonymize_customer_key(raw_id)
        amt_usd = round(float(ch.get("amount", 0)) / 100.0, 2)
        meta = ch.get("metadata") or {}
        utm = str(meta.get("utm_source") or "stripe_direct")
        seg = str(meta.get("crm_segment") or "active_customer")
        rec = by_customer.setdefault(
            anon_id,
            {
                "anon_customer_id": anon_id,
                "first_touch_utm": utm,
                "crm_segment": seg,
                "orders_count": 0,
                "ltv_usd": 0.0,
            },
        )
        rec["orders_count"] += 1
        rec["ltv_usd"] = round(rec["ltv_usd"] + amt_usd, 2)

    rows = list(by_customer.values())
    for r in rows:
        if r["orders_count"] >= 2 and r["crm_segment"] == "active_customer":
            r["crm_segment"] = "repeat_vip"
    return {"rows": rows}


def fetch_shopify_orders(
    env: dict[str, str],
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Fetch Shopify orders with immediate SHA-256 PII anonymization and UTM extraction."""
    tx = transport or _default_transport
    domain = (env.get("SHOPIFY_STORE_DOMAIN") or "").removeprefix("https://").removeprefix("http://").strip("/")
    token = (env.get("SHOPIFY_ADMIN_TOKEN") or "").strip()
    if not (domain and token):
        raise ValueError("Missing SHOPIFY_STORE_DOMAIN or SHOPIFY_ADMIN_TOKEN")

    url = f"https://{domain}/admin/api/2024-10/orders.json?status=any&limit=100"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token}, method="GET")
    resp = tx(req)

    by_customer: dict[str, dict[str, Any]] = {}
    for order in resp.get("orders", []):
        cust = order.get("customer") or {}
        raw_id = str(order.get("email") or cust.get("email") or cust.get("id") or order.get("id"))
        anon_id = anonymize_customer_key(raw_id)
        price = round(float(order.get("total_price", 0.0) or 0.0), 2)
        landing = str(order.get("landing_site") or "")
        qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(landing).query))
        utm = str(qs.get("utm_source") or "shopify_direct")
        rec = by_customer.setdefault(
            anon_id,
            {
                "anon_customer_id": anon_id,
                "first_touch_utm": utm,
                "crm_segment": "first_time_buyer",
                "orders_count": 0,
                "ltv_usd": 0.0,
            },
        )
        rec["orders_count"] += 1
        rec["ltv_usd"] = round(rec["ltv_usd"] + price, 2)
        if rec["orders_count"] >= 2:
            rec["crm_segment"] = "repeat_buyer"

    return {"rows": list(by_customer.values())}


def build_demo_fixture_telemetry() -> dict[str, dict[str, Any]]:
    """Deterministic multi-platform fixture for zero-credential local smoke tests & CI."""
    return {
        "google_ads": {
            "rows": [
                {
                    "platform": "google_ads",
                    "campaign_id": "gads-brand-01",
                    "campaign_name": "Brand Exact Search",
                    "search_term": "freecmo software",
                    "spend_usd": 420.0,
                    "impressions": 3100,
                    "clicks": 620,
                    "conversions": 14.0,
                    "revenue_usd": 2100.0,
                },
                {
                    "platform": "google_ads",
                    "campaign_id": "gads-nonbrand-02",
                    "campaign_name": "SMB Attribution Non-Brand",
                    "search_term": "marketing attribution for small business",
                    "spend_usd": 360.0,
                    "impressions": 4800,
                    "clicks": 210,
                    "conversions": 6.0,
                    "revenue_usd": 1440.0,
                },
            ],
            "active_campaigns": [
                {
                    "campaign_id": "gads-brand-01",
                    "campaign_name": "Brand Exact Search",
                    "channel": "paid_search",
                    "spend": 420.0,
                    "revenue": 2100.0,
                    "conversions": 14.0,
                    "roas": 5.0,
                    "days": 30,
                    "days_running": 30,
                },
                {
                    "campaign_id": "gads-nonbrand-02",
                    "campaign_name": "SMB Attribution Non-Brand",
                    "channel": "paid_search",
                    "spend": 360.0,
                    "revenue": 1440.0,
                    "conversions": 6.0,
                    "roas": 4.0,
                    "days": 30,
                    "days_running": 30,
                },
            ],
        },
        "meta_ads": {
            "rows": [
                {
                    "platform": "meta_instagram",
                    "campaign_id": "meta-ig-prospecting",
                    "campaign_name": "IG Reels Cold Prospecting",
                    "publisher_platform": "instagram",
                    "spend_usd": 510.0,
                    "impressions": 28000,
                    "clicks": 340,
                    "conversions": 2.0,
                    "revenue_usd": 380.0,
                }
            ],
            "active_campaigns": [
                {
                    "campaign_id": "meta-ig-prospecting",
                    "campaign_name": "IG Reels Cold Prospecting",
                    "channel": "paid_social",
                    "spend": 510.0,
                    "revenue": 380.0,
                    "conversions": 2.0,
                    "roas": 0.75,
                    "days": 16,
                    "days_running": 16,
                }
            ],
            "organic_social_posts": [
                {
                    "post_id": "ig-reel-90210",
                    "network": "instagram",
                    "media_type": "REELS",
                    "caption": "How solo founders cut wasted ad spend in 15 minutes a week",
                    "reach": 14200,
                    "saves": 310,
                    "engagement_score": 1640.0,
                    "save_or_watch_multiplier": 2.8,
                    "receipt": "data/exports/social_organic_ig_fb.csv",
                },
                {
                    "post_id": "fb-post-44120",
                    "network": "facebook",
                    "media_type": "FEED_OR_REEL",
                    "caption": "Behind the scenes of our weekly unit-economics check",
                    "reach": 2400,
                    "saves": 18,
                    "engagement_score": 585.0,
                    "save_or_watch_multiplier": 1.0,
                    "receipt": "data/exports/social_organic_ig_fb.csv",
                },
            ],
        },
        "ga4": {
            "rows": [
                {"channel_group": "Organic Search", "sessions": 4200, "conversions": 38.0, "revenue_usd": 7220.0},
                {"channel_group": "Paid Search", "sessions": 830, "conversions": 20.0, "revenue_usd": 3540.0},
                {"channel_group": "Paid Social", "sessions": 610, "conversions": 4.0, "revenue_usd": 760.0},
            ],
            "tracking_verified": True,
            "monthly_conversions": 62,
        },
        "gsc": {
            "rows": [
                {
                    "search_term": "freecmo software",
                    "clicks": 890,
                    "impressions": 2400,
                    "ctr": 0.3708,
                    "avg_position": 1.2,
                },
                {
                    "search_term": "marketing attribution for small business",
                    "clicks": 18,
                    "impressions": 1950,
                    "ctr": 0.0092,
                    "avg_position": 16.4,
                },
            ]
        },
        "stripe": {
            "rows": [
                {
                    "anon_customer_id": anonymize_customer_key("vip1@example.com"),
                    "first_touch_utm": "google_organic",
                    "crm_segment": "lapsed_vip_winback",
                    "orders_count": 3,
                    "ltv_usd": 690.0,
                },
                {
                    "anon_customer_id": anonymize_customer_key("cold1@example.com"),
                    "first_touch_utm": "meta_ig",
                    "crm_segment": "cold_paid_social",
                    "orders_count": 1,
                    "ltv_usd": 190.0,
                },
            ]
        },
    }


def _cross_join_paid_and_gsc(
    gads_rows: list[dict[str, Any]],
    gsc_rows: list[dict[str, Any]],
    allowable_cac_usd: float = 100.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive Paid<->SEO cannibalization overlaps and Paid->SEO/GEO opportunities."""
    gsc_by_term = {str(r.get("search_term", "")).lower(): r for r in gsc_rows if r.get("search_term")}
    overlaps: list[dict[str, Any]] = []
    seo_opps: list[dict[str, Any]] = []

    for row in gads_rows:
        term = str(row.get("search_term") or "").strip()
        if not term:
            continue
        t_low = term.lower()
        spend = float(to_float(row.get("spend_usd")) or 0.0)
        convs = float(to_float(row.get("conversions")) or 0.0)
        cpa = round(spend / convs, 2) if convs > 0 else 9999.0
        gsc_match = gsc_by_term.get(t_low)
        org_pos = float(gsc_match["avg_position"]) if gsc_match else 99.0

        if org_pos <= 2.0 and spend > 0:
            overlaps.append(
                {
                    "query": term,
                    "organic_position": org_pos,
                    "competitor_impression_share_pct": 3.0,
                    "monthly_paid_spend_usd": spend,
                    "receipt": "data/exports/google_ads.csv + data/exports/gsc_queries.csv",
                }
            )
        if convs >= 3.0 and cpa <= allowable_cac_usd and org_pos > 10.0:
            seo_opps.append(
                {
                    "topic": term,
                    "paid_conversions": convs,
                    "paid_cpa_usd": cpa,
                    "organic_position": org_pos,
                    "estimated_monthly_value_usd": round(max(spend, convs * 45.0), 2),
                    "receipt": "data/exports/google_ads.csv + data/exports/gsc_queries.csv",
                }
            )

    return overlaps, seo_opps


def sync_all_platforms(
    repo_root: pathlib.Path,
    platforms: list[str] | None = None,
    env: dict[str, str] | None = None,
    lookback_days: int = 30,
    demo_fixture: bool = False,
    allowable_cac_usd: float = 100.0,
    monthly_budget_usd: float = 2500.0,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    """Run read-only platform sync, write data/exports/*.csv, unify SQLite cohorts, and assemble state."""
    e = env if env is not None else dict(os.environ)
    exports_dir = repo_root / "data" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    resolver = IdentityResolver(repo_root / "data" / "radar.db")

    if demo_fixture:
        raw_telemetry = build_demo_fixture_telemetry()
        selected = list(raw_telemetry.keys()) if not platforms else [p for p in platforms if p in raw_telemetry]
    else:
        selected = platforms if platforms is not None else detect_configured_platforms(e)
        raw_telemetry = {}
        for p in selected:
            if p == "google_ads":
                raw_telemetry[p] = fetch_google_ads(e, lookback_days=lookback_days, transport=transport)
            elif p == "meta_ads":
                raw_telemetry[p] = fetch_meta_ads_and_social(e, lookback_days=lookback_days, transport=transport)
            elif p == "linkedin_ads":
                raw_telemetry[p] = fetch_linkedin_ads(e, lookback_days=lookback_days, transport=transport)
            elif p == "tiktok_ads":
                raw_telemetry[p] = fetch_tiktok_ads(e, lookback_days=lookback_days, transport=transport)
            elif p == "ga4":
                raw_telemetry[p] = fetch_ga4(e, lookback_days=lookback_days, transport=transport)
            elif p == "gsc":
                raw_telemetry[p] = fetch_gsc(e, lookback_days=lookback_days, transport=transport)
            elif p == "stripe":
                raw_telemetry[p] = fetch_stripe_revenue(e, transport=transport)
            elif p == "shopify":
                raw_telemetry[p] = fetch_shopify_orders(e, transport=transport)
            else:
                raise ValueError(f"Unsupported platform {p!r}; expected one of {SUPPORTED_PLATFORMS}")

    written_files: list[str] = []
    active_campaigns: list[dict[str, Any]] = []
    organic_social_posts: list[dict[str, Any]] = []
    gads_rows: list[dict[str, Any]] = []
    gsc_rows: list[dict[str, Any]] = []
    unified_customers = 0
    tracking_verified = True
    monthly_conversions = 0

    for p in selected:
        pdata = raw_telemetry[p]
        rows = pdata.get("rows", [])
        if p in ("google_ads", "meta_ads", "linkedin_ads", "tiktok_ads"):
            cols = [
                "platform",
                "campaign_id",
                "campaign_name",
                "search_term",
                "publisher_platform",
                "spend_usd",
                "impressions",
                "clicks",
                "conversions",
                "revenue_usd",
            ]
            written_files.append(_write_normalized_csv(exports_dir / f"{p}.csv", cols, rows))
            active_campaigns.extend(pdata.get("active_campaigns", []))
            if p == "google_ads":
                gads_rows.extend(rows)
            if p == "meta_ads" and pdata.get("organic_social_posts"):
                org_posts = pdata["organic_social_posts"]
                organic_social_posts.extend(org_posts)
                written_files.append(
                    _write_normalized_csv(
                        exports_dir / "social_organic_ig_fb.csv",
                        [
                            "post_id",
                            "network",
                            "media_type",
                            "caption",
                            "reach",
                            "saves",
                            "engagement_score",
                            "save_or_watch_multiplier",
                        ],
                        org_posts,
                    )
                )
        elif p == "ga4":
            written_files.append(
                _write_normalized_csv(
                    exports_dir / "ga4_channels.csv",
                    ["channel_group", "sessions", "conversions", "revenue_usd"],
                    rows,
                )
            )
            tracking_verified = bool(pdata.get("tracking_verified", True))
            monthly_conversions = int(pdata.get("monthly_conversions", 0))
        elif p == "gsc":
            written_files.append(
                _write_normalized_csv(
                    exports_dir / "gsc_queries.csv",
                    ["search_term", "clicks", "impressions", "ctr", "avg_position"],
                    rows,
                )
            )
            gsc_rows.extend(rows)
        elif p in ("stripe", "shopify"):
            written_files.append(
                _write_normalized_csv(
                    exports_dir / f"{p}_cohorts.csv",
                    ["anon_customer_id", "first_touch_utm", "crm_segment", "orders_count", "ltv_usd"],
                    rows,
                )
            )
            unified_customers += resolver.unify_csv_records(rows, source_kind=p)

    overlaps, seo_opps = _cross_join_paid_and_gsc(gads_rows, gsc_rows, allowable_cac_usd=allowable_cac_usd)
    if monthly_conversions == 0 and active_campaigns:
        monthly_conversions = int(round(sum(float(c.get("conversions", 0.0)) for c in active_campaigns)))

    for camp in active_campaigns:
        camp.setdefault("allowable_cac_usd", allowable_cac_usd)

    # Map SQLite cohort summary into segment ROI table for acquisition vs. retention allocation
    cohort_summary = resolver.summarize_segments()
    cohort_segments: list[dict[str, Any]] = []
    for seg in cohort_summary:
        seg_name = str(seg["crm_segment"])
        is_ret = any(k in seg_name.lower() for k in ("repeat", "vip", "winback", "retention", "active"))
        spend_est = max(50.0, float(seg["total_acq_cost_usd"] or (75.0 if is_ret else 350.0)))
        rev_est = float(seg["total_ltv_usd"] or 0.0)
        cohort_segments.append(
            {
                "segment_name": seg_name,
                "motion": "retention" if is_ret else "cold_acquisition",
                "cost_usd": round(spend_est, 2),
                "incremental_gross_profit_usd": round(rev_est * 0.65, 2),
            }
        )

    orchestrator_state: dict[str, Any] = {
        "brand_truth_path": str(repo_root / ".agents" / "brand-truth.md"),
        "guardrails_path": str(repo_root / ".agents" / "guardrails.yaml"),
        "experiment_ledger_path": str(repo_root / "experiments" / "ledger.jsonl"),
        "tracking_verified": tracking_verified,
        "site_load_sec": 2.1,
        "payback_months": 1.8,
        "max_payback_months": 3.0,
        "monthly_conversions": monthly_conversions,
        "monthly_budget_usd": monthly_budget_usd,
        "allowable_cac_usd": allowable_cac_usd,
        "reallocation_pool_usd": round(monthly_budget_usd * 0.15, 2),
        "active_campaigns": active_campaigns,
        "paid_seo_overlaps": overlaps,
        "seo_geo_opportunities": seo_opps,
        "organic_social_posts": organic_social_posts,
        "cohort_segments": cohort_segments,
    }

    state_path = repo_root / "data" / "latest_sync_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(orchestrator_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "synced_platforms": selected,
        "written_exports": written_files,
        "unified_customer_records": unified_customers,
        "state_path": str(state_path),
        "orchestrator_state": orchestrator_state,
    }
