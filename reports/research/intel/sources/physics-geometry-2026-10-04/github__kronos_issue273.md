source: https://github.com/shiyu-coder/Kronos/issues/273
fetched_utc: 2026-10-04T18:41:33Z
bytes_raw: 250308

Kronos-large Licensing Inquiry — Commercial Application on US Equities · Issue #273 · shiyu-coder/Kronos · GitHub

      Skip to content

        You signed in with another tab or window. Reload to refresh your session.
        You signed out in another tab or window. Reload to refresh your session.
        You switched accounts on another tab or window. Reload to refresh your session.

Dismiss alert

{{ message }}

        shiyu-coder

    /

      Kronos

    Public

Notifications
    You must be signed in to change notification settings

Fork
    6.6k

          Star
          39.9k

Kronos-large Licensing Inquiry — Commercial Application on US Equities #273

New issue

Copy link

New issue

Copy link

Open

Open

Kronos-large Licensing Inquiry — Commercial Application on US Equities#273

Copy link

Description

apexcodeing
opened on Apr 19, 2026

Issue body actions

Dear Yu Shi and the Kronos Team,

Congratulations on the AAAI 2026 acceptance — Kronos is genuinely the most capable financial time-series foundation model I have evaluated, and I want to thank you for releasing the mini, small, and base variants under MIT license.

My name is Andre, and I am the founder of Apex Global Strategies, where I have built Apex Alpha — a production AI-powered stock analysis platform for retail investors, currently running in private beta.

I am writing to formally inquire about a commercial license for Kronos-large (499.2M parameters).

HOW I AM CURRENTLY USING KRONOS:

I am running Kronos-base in production as the core forecasting engine of Apex Alpha, generating multi-timeframe predictions (5-minute, hourly, daily, and weekly) across a fixed watchlist of 100 large-cap US equities — the Apex 100. The model runs on a dedicated RTX 3090 GPU and has been integrated into a full pipeline alongside 15+ alternative data signal sources including FINRA short volume, congressional trading data, options flow, Reddit sentiment, insider activity, and institutional analyst ratings.

Every prediction is logged with a timestamp and automatically checked for directional accuracy at the appropriate future time window. I currently have several weeks of live prediction tracking data on US large-cap equities — a market segment your paper's primary validation did not cover.

WHY I NEED KRONOS-LARGE:

Based on your paper's results, Kronos-large materially improves performance on daily and weekly horizon forecasting — exactly the timeframes most critical for the investment decisions my users make. The base model performs well on short-term predictions but I believe the larger model's deeper representational capacity would meaningfully improve the daily and weekly signal quality.

WHAT I OFFER IN RETURN:

Beyond standard licensing fees, I can offer something potentially valuable to your research:

Real production accuracy data on US large-cap equities — directional accuracy logs across 100 symbols, multiple timeframes, tracked daily. This is a dataset your paper does not have and could be useful for validating Kronos performance on US markets.

Detailed feedback on US equity market behavior vs your primary A-share / CSI300 validation set — different volatility regimes, liquidity profiles, and trading hours.

Full attribution — Apex Alpha's platform, documentation, and any public communications will credit Kronos and link to your repository.

Willingness to sign any non-redistribution or commercial licensing agreement you require. The model would run exclusively on our own hardware and never be redistributed.

I understand Kronos-large may require institutional licensing terms, and I am fully prepared to discuss appropriate compensation. If a formal licensing agreement is required, I am happy to proceed. If Kronos-large is not yet available for commercial use, I would greatly appreciate any guidance on optimizing Kronos-base configuration for US equity daily and weekly forecasting.

Thank you for building something that is genuinely advancing what is possible for independent investors. I look forward to hearing from you.

Best regards,

Andre Nascimbeni

Founder, Apex Global Strategies

apexaibot.io

Apexlogic1@gmail.com

Reactions are currently unavailable

Activity
Sign up for free to join this conversation on GitHub. Already have an account? Sign in to comment

Metadata
Metadata

AssigneesNo one assigned

LabelsNo labels

No labels

ProjectsNo projects

MilestoneNo milestone

RelationshipsNone yet

DevelopmentNo branches or pull requests

Issue actions

Open in GitHub Copilot app

    You can’t perform that action at this time.