"""Styles globaux de l'application Streamlit."""

import streamlit as st

def inject_app_styles():
    """Appliquer une identité visuelle moderne sans modifier les widgets métier."""
    st.markdown(
        """
        <style>
        :root {
            --ca-green: #007a4d;
            --ca-dark: #073b2c;
            --ca-soft: #edf7f2;
            --ca-border: rgba(15, 63, 47, 0.12);
        }
        .stApp {
            background:
                radial-gradient(circle at 86% 3%, rgba(0, 122, 77, .08), transparent 25rem),
                #f7faf8;
        }
        [data-testid="stSidebar"] {
            background: #f7f9f8;
            border-right: 1px solid #dfe8e3;
            min-width: 310px;
            max-width: 310px;
            box-shadow: 8px 0 28px rgba(7, 59, 44, .06);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: 1.35rem 1.15rem 1.25rem;
        }
        [data-testid="stSidebar"] * {
            color: #173f32;
        }
        [data-testid="stSidebar"] [data-baseweb="input"] > div {
            background: #ffffff;
            border-color: #cadbd3;
        }
        [data-testid="stSidebar"] input {
            color: #173f32 !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: #dfe8e3;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 3rem;
            border-radius: .75rem;
            border: 1px solid transparent;
            background: transparent;
            justify-content: flex-start;
            padding-inline: .85rem;
            font-weight: 650;
            box-shadow: none;
            transition: background .16s ease, border-color .16s ease;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: #edf5f1;
            border-color: #d3e5dc;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #086b48;
            border-color: #086b48;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] * {
            color: #ffffff !important;
            font-weight: 700;
        }
        .st-key-sidebar_brand {
            padding-bottom: 1rem;
            border-bottom: 1px solid #dfe8e3;
        }
        .st-key-sidebar_brand [data-testid="stImage"] img {
            border-radius: .6rem;
            background: #ffffff;
            padding: .22rem;
        }
        .st-key-sidebar_intro {
            padding: 1.1rem .15rem .45rem;
        }
        .st-key-sidebar_intro h2 {
            margin-bottom: .15rem;
            color: #073b2c;
        }
        .st-key-sidebar_intro p {
            color: #64776f !important;
        }
        .st-key-sidebar_progress {
            margin: .55rem 0 1rem;
            padding: .9rem 1rem;
            border: 1px solid #dce8e2;
            border-radius: .9rem;
            background: #ffffff;
        }
        .st-key-sidebar_progress [data-testid="stProgress"] > div > div {
            background: #0b8a5b;
        }
        .st-key-sidebar_nav {
            padding-top: .2rem;
        }
        .sidebar-step-hint {
            margin: -.45rem .85rem .5rem 2.85rem;
            color: #718078;
            font-size: .75rem;
            line-height: 1.25;
        }
        .st-key-sidebar_support {
            margin-top: 1.25rem;
            padding-top: 1rem;
            border-top: 1px solid #dfe8e3;
        }
        .st-key-sidebar_profile {
            margin-top: .8rem;
            padding-top: 1rem;
            border-top: 1px solid #dfe8e3;
        }
        .st-key-sidebar_profile p {
            margin-bottom: .15rem;
        }
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .st-key-assistant_dock {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            width: min(410px, calc(100vw - 2.5rem));
            max-height: min(760px, calc(100vh - 2.5rem));
            z-index: 9999;
            background-color: #edf7f2 !important;
            border-radius: 1.35rem;
            overflow: hidden;
            box-shadow: 0 22px 65px rgba(7, 59, 44, 0.24);
        }
        .st-key-assistant_dock > div,
        .st-key-assistant_dock [data-testid="stVerticalBlockBorderWrapper"] {
            min-width: 0;
        }
        .st-key-assistant_dock [data-testid="stVerticalBlockBorderWrapper"] {
            overflow: hidden;
            background: #edf7f2;
            border: 1px solid rgba(0, 122, 77, .18);
            border-radius: 1.35rem;
            box-shadow: 0 22px 65px rgba(7, 59, 44, .24);
            backdrop-filter: blur(16px);
        }
        .st-key-assistant_launcher {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            width: 235px;
            z-index: 9999;
        }
        .st-key-assistant_launcher button {
            min-height: 3.5rem;
            border: 0;
            border-radius: 999px;
            color: #ffffff;
            background: linear-gradient(120deg, #073b2c 0%, #007a4d 100%);
            box-shadow: 0 14px 35px rgba(7, 59, 44, .28);
            font-weight: 750;
        }
        .st-key-assistant_launcher button:hover {
            transform: translateY(-2px);
            box-shadow: 0 18px 42px rgba(7, 59, 44, .34);
        }
        .st-key-assistant_close button {
            width: 2.55rem;
            min-width: 2.55rem;
            height: 2.55rem;
            min-height: 2.55rem;
            padding: 0;
            border-radius: 999px;
            font-size: 1.35rem;
            line-height: 1;
        }
        .st-key-assistant_dock [data-testid="stChatMessage"] {
            padding-block: .7rem;
        }
        .st-key-assistant_dock [data-testid="stChatInput"] {
            border-radius: 1rem;
        }
        .st-key-journey_step button {
            min-height: 3.2rem;
        }
        @media (max-width: 700px) {
            [data-testid="stSidebar"] {
                min-width: min(330px, 88vw);
                max-width: min(330px, 88vw);
            }
            .st-key-assistant_dock {
                right: .65rem;
                left: .65rem;
                bottom: .65rem;
                width: auto;
                max-height: calc(100vh - 1.3rem);
            }
            .st-key-assistant_launcher {
                right: .75rem;
                bottom: .75rem;
                width: min(225px, calc(100vw - 1.5rem));
            }
        }
        .ca-hero {
            padding: 2.1rem 2.2rem;
            border-radius: 1.35rem;
            background: linear-gradient(120deg, #073b2c 0%, #007a4d 68%, #1d9d69 100%);
            color: white;
            box-shadow: 0 18px 46px rgba(7,59,44,.18);
            margin-bottom: 1.4rem;
        }
        .ca-eyebrow {
            font-size: .76rem;
            font-weight: 800;
            letter-spacing: .12em;
            opacity: .78;
            margin-bottom: .55rem;
        }
        .ca-hero h1 {
            color: white;
            font-size: clamp(2rem, 4vw, 3.2rem);
            line-height: 1.05;
            margin: 0 0 .7rem;
        }
        .ca-hero p {
            max-width: 760px;
            font-size: 1.05rem;
            opacity: .9;
            margin: 0;
        }
        .ca-section-title {
            margin: 2.1rem 0 .25rem;
            color: #073b2c;
            font-size: 1.5rem;
            font-weight: 800;
        }
        .journey-note {
            padding: .85rem 1rem;
            border-radius: .9rem;
            background: #edf7f2;
            border: 1px solid rgba(0,122,77,.16);
            color: #164a38;
        }
        .ca-article {
            min-height: 235px;
            padding: 1.35rem;
            border-radius: 1.1rem;
            background: rgba(255,255,255,.92);
            border: 1px solid var(--ca-border);
            box-shadow: 0 10px 28px rgba(7,59,44,.07);
        }
        .ca-article:hover {
            transform: translateY(-3px);
            box-shadow: 0 16px 36px rgba(7,59,44,.11);
            transition: all .18s ease;
        }
        .ca-article .icon {
            display: inline-grid;
            place-items: center;
            width: 2.55rem;
            height: 2.55rem;
            border-radius: .8rem;
            background: var(--ca-soft);
            font-size: 1.25rem;
        }
        .ca-article h3 {
            color: #073b2c;
            margin: .95rem 0 .45rem;
            font-size: 1.08rem;
        }
        .ca-article p {
            color: #52645d;
            font-size: .92rem;
            line-height: 1.55;
        }
        .ca-tag {
            display: inline-block;
            margin-top: .7rem;
            color: #007a4d;
            font-size: .78rem;
            font-weight: 800;
        }
        .st-key-home_offer_card [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-home_estimate_card [data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 245px;
            padding: .35rem;
        }
        .st-key-home_help_banner [data-testid="stVerticalBlockBorderWrapper"] {
            background: linear-gradient(100deg, #f1f8f5, #ffffff);
            border-color: rgba(0, 122, 77, .18);
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.92);
            border: 1px solid var(--ca-border);
            border-radius: 1rem;
            padding: .75rem 1rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--ca-border);
            border-radius: 1rem;
            background: rgba(255,255,255,.88);
        }

        /* ==================================================
           FINITION PRODUIT — INTERFACE CLIENT
           ================================================== */
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {
            display: none !important;
        }
        header[data-testid="stHeader"] {
            background: transparent;
        }
        .block-container {
            width: min(100%, 1320px);
            max-width: 1320px;
            padding: 1.65rem 2.3rem 4rem;
        }
        [data-testid="stSidebar"] {
            min-width: 292px;
            max-width: 292px;
            background: #fbfcfb;
            box-shadow: 10px 0 34px rgba(7, 59, 44, .045);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: 1.15rem 1rem 1.15rem;
        }
        .st-key-sidebar_brand {
            padding: 0 .2rem .9rem;
        }
        .st-key-sidebar_intro {
            padding: .85rem .2rem .25rem;
        }
        .st-key-sidebar_intro h2 {
            font-size: 1.25rem;
        }
        .st-key-sidebar_progress {
            margin: .55rem 0 .9rem;
            padding: .9rem;
            border-radius: .85rem;
            box-shadow: 0 4px 18px rgba(7, 59, 44, .04);
        }
        .sidebar-progress-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .75rem;
            margin-bottom: .65rem;
            color: #173f32;
            font-size: .82rem;
            font-weight: 750;
        }
        .sidebar-progress-track {
            height: 8px;
            overflow: hidden;
            border-radius: 999px;
            background: #e2ece7;
        }
        .sidebar-progress-fill {
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #08734e, #21a36f);
        }
        .sidebar-progress-copy {
            margin-top: .6rem;
            color: #667a71;
            font-size: .76rem;
            line-height: 1.35;
        }
        .st-key-sidebar_nav [data-testid="stButton"] {
            margin-bottom: .12rem;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 2.65rem;
            border-radius: .65rem;
            padding-inline: .75rem;
            font-size: .9rem;
        }
        .sidebar-step-hint {
            margin: -.2rem .65rem .45rem 2.55rem;
            color: #7b8c84;
            font-size: .71rem;
        }
        .sidebar-section-label {
            margin: .8rem .25rem .35rem;
            color: #819188;
            font-size: .69rem;
            font-weight: 800;
            letter-spacing: .09em;
        }
        .st-key-sidebar_support {
            margin-top: .7rem;
            padding-top: .75rem;
        }
        .st-key-sidebar_profile {
            margin-top: .7rem;
            padding: .85rem .2rem 0;
        }
        .sidebar-user-card {
            padding: .75rem .8rem;
            border: 1px solid #dce8e2;
            border-radius: .8rem;
            background: #ffffff;
        }
        .sidebar-user-name {
            overflow: hidden;
            color: #173f32;
            font-size: .86rem;
            font-weight: 750;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .sidebar-user-email {
            overflow: hidden;
            margin-top: .18rem;
            color: #74877e;
            font-size: .72rem;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ca-hero {
            position: relative;
            overflow: hidden;
            padding: 2.2rem 2.35rem;
            border-radius: 1.15rem;
            margin-bottom: 1rem;
            box-shadow: 0 20px 48px rgba(7, 59, 44, .16);
        }
        .ca-hero::after {
            content: "";
            position: absolute;
            width: 270px;
            height: 270px;
            right: -75px;
            top: -120px;
            border: 1px solid rgba(255,255,255,.16);
            border-radius: 50%;
            box-shadow: 0 0 0 44px rgba(255,255,255,.035),
                        0 0 0 88px rgba(255,255,255,.025);
        }
        .ca-hero h1 {
            max-width: 820px;
            font-size: clamp(2rem, 3.2vw, 2.8rem);
            line-height: 1.08;
        }
        .ca-hero p {
            max-width: 760px;
            font-size: 1rem;
            line-height: 1.55;
        }
        .ca-hero .ca-tag {
            margin-top: 1rem;
            padding: .34rem .58rem;
            border: 1px solid rgba(255,255,255,.2);
            border-radius: 999px;
            color: #ffffff;
            background: rgba(255,255,255,.1);
            font-size: .68rem;
            letter-spacing: .04em;
        }
        .st-key-home_project_summary [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-home_primary_action [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-home_secondary_action [data-testid="stVerticalBlockBorderWrapper"] {
            padding: .25rem .35rem;
            border-radius: 1rem;
            background: #ffffff;
            box-shadow: 0 8px 26px rgba(7, 59, 44, .055);
        }
        .home-status-line {
            display: flex;
            align-items: center;
            gap: .5rem;
            color: #08734e;
            font-size: .79rem;
            font-weight: 750;
        }
        .home-status-dot {
            width: .5rem;
            height: .5rem;
            border-radius: 50%;
            background: #16a36c;
            box-shadow: 0 0 0 4px rgba(22,163,108,.11);
        }
        .ca-article {
            min-height: 205px;
            box-shadow: 0 7px 24px rgba(7,59,44,.055);
        }
        @media (max-width: 900px) {
            .block-container {
                padding-inline: 1rem;
            }
        }

        /* ==================================================
           IDENTITÉ INSTITUTIONNELLE GCAM
           Inspirée du site officiel, adaptée au parcours crédit
           ================================================== */
        :root {
            --cam-forest: #173e24;
            --cam-forest-deep: #102f1b;
            --cam-green: #159447;
            --cam-lime: #8bcf31;
            --cam-red: #e5242a;
            --cam-ink: #202824;
            --cam-muted: #65736b;
            --cam-line: #dde4df;
            --cam-surface: #ffffff;
        }
        html, body, [class*="css"] {
            font-family: Arial, Helvetica, sans-serif;
        }
        .stApp {
            color: var(--cam-ink);
            background: #ffffff;
        }
        header[data-testid="stHeader"] {
            height: 0 !important;
            min-height: 0 !important;
            background: transparent;
        }
        [data-testid="stSidebar"],
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        .block-container {
            width: 100%;
            max-width: none;
            padding-top: 1rem;
            padding-right: clamp(1rem, 3vw, 3.5rem);
            padding-left: clamp(1rem, 3vw, 3.5rem);
        }
        .cam-site-header {
            margin-bottom: 0;
        }
        .cam-utility-bar {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 1.25rem;
            min-height: 2.35rem;
            padding: .35rem 1.1rem;
            color: #ffffff;
            background: var(--cam-forest-deep);
            font-size: .74rem;
            letter-spacing: .05em;
        }
        .cam-universe {
            padding: .45rem 1.05rem;
            border-radius: 0 0 1rem 1rem;
            background: linear-gradient(90deg, #69b92e, var(--cam-lime));
            font-weight: 750;
        }
        .cam-secure {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            padding: .34rem .78rem;
            border: 1px solid rgba(255,255,255,.55);
            border-radius: 999px;
        }
        .cam-main-nav {
            display: flex;
            align-items: center;
            min-height: 5.7rem;
            padding: .75rem 1.45rem;
            border: 1px solid #e3e6e4;
            background: #ffffff;
            box-shadow: 0 10px 30px rgba(16,47,27,.08);
        }
        .cam-product-title {
            margin-left: auto;
            color: var(--cam-forest);
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: 1.05rem;
            font-weight: 800;
            letter-spacing: .08em;
        }
        .cam-brand {
            display: flex;
            align-items: center;
            gap: .85rem;
            min-width: 250px;
            padding-right: 1.25rem;
        }
        .cam-brand img {
            width: 145px;
            max-height: 62px;
            object-fit: contain;
        }
        .cam-brand-fallback {
            color: var(--cam-forest);
            font-size: .92rem;
            font-weight: 800;
            line-height: 1.15;
        }
        .cam-nav-items {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0;
            width: 100%;
        }
        .cam-nav-item {
            padding: .42rem 1rem;
            border-right: 1px solid #e2e5e3;
            color: #1c251f;
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: .77rem;
            font-weight: 800;
            letter-spacing: .035em;
            white-space: nowrap;
        }
        .cam-nav-item.is-active {
            color: var(--cam-green);
        }
        .cam-nav-space {
            margin-left: 1.1rem;
            padding: .72rem 1rem;
            border-radius: 999px;
            color: #ffffff;
            background: linear-gradient(105deg, #24995d, #94dc44);
            font-size: .76rem;
            font-weight: 800;
            white-space: nowrap;
        }
        .cam-breadcrumb {
            padding: .7rem .2rem 0;
            color: #708078;
            font-size: .72rem;
        }
        .cam-breadcrumb strong {
            color: var(--cam-forest);
        }
        .st-key-cam_top_navigation {
            margin-top: -1px;
            padding: .55rem .7rem;
            border: 1px solid #e3e6e4;
            background: #ffffff;
            box-shadow: 0 12px 30px rgba(16,47,27,.06);
        }
        .st-key-cam_top_navigation [data-testid="stHorizontalBlock"] {
            align-items: center;
            gap: .2rem;
        }
        .st-key-cam_top_navigation .stButton > button,
        .st-key-cam_top_navigation [data-testid="stPopover"] > button {
            min-height: 2.9rem;
            border: 0;
            border-right: 1px solid #e5e8e6;
            border-radius: 0;
            color: #243029;
            background: #ffffff;
            box-shadow: none;
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: .76rem;
            font-weight: 800;
            letter-spacing: .025em;
            white-space: nowrap;
        }
        .st-key-cam_top_navigation .stButton > button:hover,
        .st-key-cam_top_navigation [data-testid="stPopover"] > button:hover {
            color: var(--cam-green);
            background: #f3f9f5;
        }
        .st-key-cam_top_navigation .stButton > button[kind="primary"] {
            color: var(--cam-green);
            border-bottom: 2px solid var(--cam-red);
            background: #f3f9f5;
        }
        .st-key-cam_top_navigation [data-testid="stPopover"] > button {
            border-right: 0;
            border-radius: 999px;
            color: #ffffff;
            background: linear-gradient(105deg, #24995d, #94dc44);
        }
        .st-key-top_nav_logo button {
            min-height: 4.25rem !important;
            border-right: 1px solid #e2e5e3 !important;
            background-color: #ffffff !important;
            background-position: left center !important;
            background-repeat: no-repeat !important;
            background-size: contain !important;
            box-shadow: none !important;
        }
        .st-key-top_nav_logo button:hover {
            background-color: #f8faf8 !important;
        }
        .cam-space-profile {
            margin-bottom: .8rem;
            padding: .75rem .8rem;
            border: 1px solid var(--cam-line);
            background: #f8faf8;
        }
        .cam-space-name {
            color: var(--cam-forest);
            font-weight: 800;
        }
        .cam-space-email {
            margin-top: .15rem;
            color: var(--cam-muted);
            font-size: .78rem;
        }
        .cam-space-progress {
            margin: .25rem 0 .55rem;
            color: var(--cam-muted);
            font-size: .78rem;
        }
        .ca-hero {
            isolation: isolate;
            min-height: 330px;
            display: flex;
            align-items: center;
            padding: 3.5rem 3.25rem;
            border-radius: .15rem;
            background-image:
                linear-gradient(90deg, rgba(16,47,27,.96) 0%, rgba(23,62,36,.90) 48%, rgba(23,62,36,.48) 100%),
                var(--cam-hero-image, linear-gradient(120deg, #102f1b, #225e36));
            background-position: center;
            background-size: cover;
            box-shadow: none;
        }
        .ca-hero::after {
            display: none;
        }
        .ca-hero-content {
            position: relative;
            z-index: 1;
            max-width: 790px;
        }
        .ca-eyebrow {
            color: #b7e879;
            font-size: .72rem;
            letter-spacing: .16em;
            opacity: 1;
        }
        .ca-hero h1 {
            margin-top: .65rem;
            color: #ffffff;
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: clamp(2.25rem, 4.5vw, 3.75rem);
            font-weight: 400;
            letter-spacing: .015em;
            line-height: 1.05;
            text-transform: uppercase;
        }
        .ca-hero p {
            max-width: 720px;
            margin-top: 1.15rem;
            color: rgba(255,255,255,.92);
            font-size: 1rem;
            line-height: 1.65;
        }
        .ca-hero .ca-tag {
            margin-top: 1.4rem;
            padding: 0 0 .35rem;
            border: 0;
            border-bottom: 2px solid var(--cam-red);
            border-radius: 0;
            color: #ffffff;
            background: transparent;
        }
        .ca-section-title {
            margin-top: 2.8rem;
            color: #1f2722;
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: 1.8rem;
            font-weight: 400;
            letter-spacing: .025em;
            text-align: center;
            text-transform: uppercase;
        }
        .ca-section-title::after {
            content: "";
            display: block;
            width: 48px;
            height: 2px;
            margin: .9rem auto 1.2rem;
            background: var(--cam-red);
        }
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stMetric"] {
            border-color: var(--cam-line);
            border-radius: .25rem;
            background: #ffffff;
            box-shadow: none;
        }
        .stButton > button,
        .stFormSubmitButton > button {
            min-height: 2.85rem;
            border-radius: 999px;
            font-weight: 750;
        }
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            border-color: transparent;
            background: linear-gradient(105deg, #187f4f, #77c83a);
            box-shadow: 0 8px 18px rgba(24,127,79,.17);
        }
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {
            border-color: transparent;
            background: linear-gradient(105deg, #126b42, #69ba31);
        }
        [data-baseweb="tab-list"] {
            gap: .35rem;
            border-bottom: 1px solid var(--cam-line);
        }
        [data-baseweb="tab"] {
            border-radius: .2rem .2rem 0 0;
            font-weight: 700;
        }
        [aria-selected="true"][data-baseweb="tab"] {
            color: var(--cam-green);
            border-bottom-color: var(--cam-red);
        }
        [data-testid="stSidebar"] {
            border-top: .45rem solid var(--cam-lime);
            border-right: 1px solid var(--cam-line);
            background: #f8faf8;
            box-shadow: 6px 0 24px rgba(16,47,27,.045);
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            border-radius: .25rem;
            background: var(--cam-forest);
            box-shadow: none;
        }
        [data-testid="stSidebar"] .stButton > button {
            border-radius: .25rem;
        }
        .sidebar-progress-fill {
            background: linear-gradient(90deg, var(--cam-green), var(--cam-lime));
        }
        .st-key-assistant_launcher button {
            border-radius: 999px;
            background: linear-gradient(105deg, var(--cam-forest), var(--cam-green));
        }
        @media (max-width: 1050px) {
            .cam-brand { min-width: 190px; }
            .cam-brand img { width: 125px; }
            .cam-nav-item { padding-inline: .55rem; font-size: .68rem; }
            .cam-nav-space { margin-left: .55rem; }
        }
        @media (max-width: 760px) {
            .cam-utility-bar { justify-content: space-between; }
            .cam-breadcrumb { display: none; }
            .st-key-cam_top_navigation [data-testid="stHorizontalBlock"] {
                overflow-x: auto;
                flex-wrap: nowrap;
            }
            .st-key-cam_top_navigation [data-testid="column"] {
                min-width: 135px;
            }
            .st-key-cam_top_navigation [data-testid="column"]:first-child {
                min-width: 180px;
            }
            .ca-hero { min-height: 280px; padding: 2.5rem 1.35rem; }
            .ca-hero h1 { font-size: 2.05rem; }
        }

        /* ==================================================
           EN-TÊTE ET BANNIÈRE — FINITION INSTITUTIONNELLE
           ================================================== */
        .cam-utility-bar {
            justify-content: space-between;
            min-height: 2.7rem;
            padding: 0 1.25rem;
            background: #10351f;
        }
        .cam-corporate {
            color: rgba(255,255,255,.78);
            font-size: .68rem;
            font-weight: 700;
            letter-spacing: .095em;
        }
        .cam-utility-actions {
            display: flex;
            align-items: center;
            gap: .75rem;
        }
        .cam-universe {
            padding: .52rem .95rem;
            border-radius: 0 0 .9rem .9rem;
            box-shadow: 0 4px 12px rgba(0,0,0,.08);
        }
        .cam-secure {
            padding: .38rem .78rem;
            font-size: .67rem;
        }
        .st-key-cam_top_navigation {
            padding: .42rem 1rem;
            border: 1px solid #e6ebe8;
            box-shadow: 0 12px 32px rgba(16,53,31,.07);
        }
        .st-key-cam_top_navigation [data-testid="stHorizontalBlock"] {
            min-height: 4.65rem;
        }
        .st-key-cam_top_navigation .stButton > button,
        .st-key-cam_top_navigation [data-testid="stPopover"] button {
            min-height: 3.35rem;
            padding-inline: .7rem;
            font-size: .72rem;
            letter-spacing: .04em;
        }
        .st-key-cam_top_navigation .stButton > button[kind="primary"] {
            color: #118c49;
            border-bottom: 2px solid var(--cam-red);
            background: linear-gradient(180deg, #ffffff, #f4faf6);
        }
        .st-key-cam_top_navigation [data-testid="column"]:last-child
        [data-testid="stPopover"] button {
            border: 0;
            border-radius: 999px;
            color: #ffffff;
            background: linear-gradient(105deg, #208f55, #83cf38);
            box-shadow: 0 8px 20px rgba(32,143,85,.18);
        }
        .st-key-top_nav_logo button {
            justify-content: flex-start;
            min-height: 4.4rem !important;
            padding-left: 5.2rem !important;
            color: #173e24 !important;
            font-family: Arial, Helvetica, sans-serif !important;
            font-size: .72rem !important;
            font-weight: 800 !important;
            line-height: 1.15 !important;
            letter-spacing: .025em !important;
            text-align: left !important;
        }
        .st-key-top_nav_logo button p {
            max-width: 125px;
            white-space: normal;
        }
        .cam-breadcrumb {
            padding: .85rem .15rem .55rem;
            color: #7a8980;
            font-size: .7rem;
        }
        .ca-hero {
            min-height: 390px;
            padding: 2.75rem 3rem;
            border-radius: .2rem;
            background-image:
                radial-gradient(circle at 86% 18%, rgba(139,207,49,.22), transparent 21rem),
                linear-gradient(105deg, rgba(13,50,29,.98) 0%, rgba(20,76,42,.97) 58%, rgba(25,102,55,.92) 100%),
                var(--cam-hero-image, linear-gradient(120deg, #102f1b, #225e36));
            box-shadow: 0 18px 45px rgba(16,53,31,.12);
        }
        .cam-hero-grid {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: minmax(0, 1.35fr) minmax(310px, .65fr);
            align-items: center;
            gap: clamp(2rem, 5vw, 5rem);
            width: 100%;
        }
        .ca-hero-content {
            max-width: 760px;
        }
        .ca-hero h1 {
            max-width: 720px;
            margin-top: .75rem;
            font-size: clamp(2.25rem, 3.7vw, 3.35rem);
            font-weight: 400;
            letter-spacing: .008em;
            line-height: 1.08;
        }
        .ca-hero p {
            max-width: 650px;
            margin-top: 1rem;
            font-size: .98rem;
        }
        .ca-hero .ca-tag {
            display: inline-block;
            margin-top: 1.2rem;
            font-size: .66rem;
            letter-spacing: .065em;
        }
        .cam-hero-trust {
            display: flex;
            flex-wrap: wrap;
            gap: .65rem 1.25rem;
            margin-top: 1.55rem;
            color: rgba(255,255,255,.82);
            font-size: .72rem;
        }
        .cam-hero-trust span {
            display: inline-flex;
            align-items: center;
            gap: .38rem;
        }
        .cam-hero-trust i {
            width: .42rem;
            height: .42rem;
            border-radius: 50%;
            background: #9cdb4d;
            box-shadow: 0 0 0 3px rgba(156,219,77,.12);
        }
        .cam-journey-card {
            padding: 1.45rem 1.4rem 1.25rem;
            border: 1px solid rgba(255,255,255,.22);
            background: rgba(255,255,255,.10);
            box-shadow: 0 18px 38px rgba(0,0,0,.12);
            backdrop-filter: blur(12px);
        }
        .cam-journey-kicker {
            color: #bce77f;
            font-size: .65rem;
            font-weight: 800;
            letter-spacing: .12em;
        }
        .cam-journey-title {
            margin: .4rem 0 1.05rem;
            color: #ffffff;
            font-family: "Arial Narrow", Arial, sans-serif;
            font-size: 1.28rem;
            font-weight: 500;
        }
        .cam-journey-row {
            display: grid;
            grid-template-columns: 2rem 1fr auto;
            align-items: center;
            gap: .65rem;
            min-height: 2.8rem;
            border-top: 1px solid rgba(255,255,255,.13);
            color: rgba(255,255,255,.72);
            font-size: .76rem;
        }
        .cam-journey-row:first-of-type {
            border-top: 0;
        }
        .cam-journey-number {
            color: rgba(255,255,255,.46);
            font-size: .68rem;
            font-weight: 800;
        }
        .cam-journey-row.is-current,
        .cam-journey-row.is-done {
            color: #ffffff;
            font-weight: 700;
        }
        .cam-journey-row.is-current .cam-journey-number {
            color: #bce77f;
        }
        .cam-journey-state {
            color: #bce77f;
            font-size: .62rem;
            font-weight: 800;
            letter-spacing: .05em;
        }
        @media (max-width: 1000px) {
            .cam-corporate { display: none; }
            .cam-utility-bar { justify-content: flex-end; }
            .cam-hero-grid { grid-template-columns: 1fr; }
            .cam-journey-card { display: none; }
            .ca-hero { min-height: 330px; }
        }
        @media (max-width: 760px) {
            .st-key-top_nav_logo button {
                padding-left: 4.5rem !important;
            }
            .ca-hero {
                min-height: 315px;
                padding: 2.2rem 1.35rem;
            }
            .ca-hero h1 { font-size: 2.15rem; }
            .cam-hero-trust { display: none; }
        }

        /* ==================================================
           ACCUEIL — PARCOURS PREMIUM INSPIRÉ DU SITE CAM
           ================================================== */
        :root {
            --cam-gold: #c6a04b;
            --cam-cream: #f7f4ec;
            --cam-ink: #112d23;
        }
        .stApp {
            background: var(--cam-cream);
        }
        .block-container {
            width: min(100%, 1680px);
            max-width: 1680px;
            padding: 0 2.4rem 3.5rem;
        }
        .cam-site-header {
            display: block;
            margin-inline: -2.4rem;
        }
        .cam-utility-bar {
            min-height: 3.45rem;
            padding-inline: clamp(1.5rem, 7vw, 7rem);
            background: #063526;
        }
        .cam-corporate {
            color: #ffffff;
            font-size: .78rem;
            letter-spacing: .015em;
            text-transform: none;
        }
        .cam-universe {
            color: #123627;
            background: var(--cam-gold);
        }
        .cam-secure {
            border-color: rgba(255,255,255,.22);
            color: rgba(255,255,255,.9);
        }
        .st-key-cam_top_navigation {
            margin-inline: -2.4rem;
            padding: 0 clamp(1.4rem, 7vw, 7rem);
            border: 0;
            border-bottom: 1px solid #e7e2d7;
            background: #ffffff;
            box-shadow: none;
        }
        .st-key-cam_top_navigation [data-testid="stHorizontalBlock"] {
            min-height: 5.2rem;
            gap: 0;
        }
        .st-key-cam_top_navigation .stButton > button,
        .st-key-cam_top_navigation [data-testid="stPopover"] > button {
            min-height: 5.15rem;
            border-right: 1px solid #ece8df;
            color: #405048;
            background: #ffffff;
            font-family: Arial, Helvetica, sans-serif;
            font-size: .82rem;
            font-weight: 650;
            letter-spacing: 0;
            text-transform: none;
        }
        .st-key-cam_top_navigation .stButton > button[kind="primary"] {
            color: #0a4935;
            border-bottom: 3px solid var(--cam-gold);
            background: #ffffff;
        }
        .st-key-cam_top_navigation .stButton > button:disabled {
            color: #8e978f !important;
            opacity: 1;
            background: #ffffff !important;
        }
        .st-key-cam_top_navigation [data-testid="column"]:last-child
        [data-testid="stPopover"] > button {
            border: 0;
            border-left: 1px solid #ece8df;
            border-radius: 0;
            color: #143c2d;
            background: #ffffff;
            box-shadow: none;
        }
        .st-key-top_nav_logo button {
            min-height: 5.15rem !important;
            padding-left: 5.25rem !important;
            background-position: left 1rem center !important;
            background-size: 3.1rem auto !important;
        }
        .cam-breadcrumb {
            padding: 1.4rem clamp(.2rem, 2vw, 1.2rem) 1.1rem;
            font-size: .79rem;
        }

        .st-key-cam_home_experience {
            margin: .2rem auto 0;
            overflow: hidden;
            border: 1px solid rgba(20,61,45,.08);
            border-radius: 1.7rem;
            background: #ffffff;
            box-shadow: 0 24px 60px rgba(15,55,40,.14);
        }
        .st-key-cam_home_experience > div > div[data-testid="stHorizontalBlock"] {
            gap: 0;
        }
        .st-key-cam_home_experience [data-testid="column"] {
            min-width: 0;
        }
        .st-key-cam_home_intro {
            min-height: 590px;
            padding: clamp(3rem, 5vw, 5rem) clamp(2.3rem, 5vw, 5rem) 2.3rem;
            color: #ffffff;
            background:
                radial-gradient(circle at 95% 2%, rgba(198,160,75,.12), transparent 18rem),
                #0b412f;
        }
        .st-key-cam_home_journey {
            min-height: 590px;
            padding: clamp(2.8rem, 4vw, 4.1rem) clamp(2rem, 4vw, 3.7rem) 2.2rem;
            color: var(--cam-ink);
            background: #fffdf8;
        }
        .cam-home-intro-copy .ca-eyebrow {
            display: flex;
            align-items: center;
            gap: .7rem;
            color: var(--cam-gold);
            font-size: .82rem;
            font-weight: 700;
            letter-spacing: .015em;
            text-transform: none;
        }
        .cam-home-intro-copy .ca-eyebrow span {
            width: .48rem;
            height: .48rem;
            border-radius: 50%;
            background: var(--cam-gold);
        }
        .cam-home-intro-copy h1 {
            max-width: 690px;
            margin: 1.5rem 0 1.5rem;
            color: #ffffff;
            font-family: Georgia, "Times New Roman", serif;
            font-size: clamp(3rem, 4.6vw, 5rem);
            font-weight: 500;
            letter-spacing: -.035em;
            line-height: .98;
            text-transform: none;
        }
        .cam-home-intro-copy p {
            max-width: 720px;
            margin-bottom: 1.7rem;
            color: rgba(255,255,255,.83);
            font-size: 1.06rem;
            line-height: 1.55;
        }
        .st-key-cam_home_intro .stButton > button {
            min-height: 3.2rem;
            border-radius: .65rem;
            border-color: rgba(255,255,255,.25);
            color: #ffffff;
            background: transparent;
            box-shadow: none;
        }
        .st-key-cam_home_intro .stButton > button[kind="primary"] {
            border-color: var(--cam-gold);
            color: #123828;
            background: var(--cam-gold);
        }
        .cam-hero-trust {
            display: flex;
            justify-content: space-between;
            gap: .8rem 1.2rem;
            margin-top: 1.65rem;
            padding-top: 1.35rem;
            border-top: 1px solid rgba(255,255,255,.18);
            color: rgba(255,255,255,.72);
            font-size: .76rem;
        }
        .cam-journey-kicker {
            color: #9b762c;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .07em;
        }
        .cam-journey-title {
            margin: .55rem 0 .25rem;
            color: #102f24;
            font-family: Arial, Helvetica, sans-serif;
            font-size: 1.28rem;
            font-weight: 800;
        }
        .cam-journey-subtitle {
            color: #89948d;
            font-size: .82rem;
        }
        .cam-journey-progress {
            height: .42rem;
            margin: 2rem 0 1.35rem;
            overflow: hidden;
            border-radius: 999px;
            background: #eeeade;
        }
        .cam-journey-progress span {
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #0b6749, var(--cam-gold));
        }
        .cam-journey-list {
            position: relative;
        }
        .cam-journey-list::before {
            content: "";
            position: absolute;
            top: 2rem;
            bottom: 2rem;
            left: 1.24rem;
            width: 1px;
            background: #ded8c9;
        }
        .cam-journey-row {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 2.55rem minmax(0, 1fr) auto;
            align-items: center;
            gap: .85rem;
            min-height: 4.55rem;
            border: 0;
            color: #6f7973;
            font-size: .82rem;
        }
        .cam-journey-number {
            display: grid;
            place-items: center;
            width: 2.35rem;
            height: 2.35rem;
            border: 1px solid #d9d3c5;
            border-radius: 50%;
            color: #8d9790;
            background: #fffdf8;
            font-size: .76rem;
            font-weight: 800;
        }
        .cam-journey-copy {
            display: flex;
            flex-direction: column;
            gap: .22rem;
        }
        .cam-journey-copy strong {
            color: #32453d;
            font-size: .92rem;
        }
        .cam-journey-copy small {
            color: #909991;
            font-size: .76rem;
        }
        .cam-journey-row.is-current .cam-journey-number,
        .cam-journey-row.is-done .cam-journey-number {
            border-color: #0b5f45;
            color: #ffffff;
            background: #0b5f45;
            box-shadow: 0 0 0 5px rgba(11,95,69,.09);
        }
        .cam-journey-row.is-current .cam-journey-copy strong,
        .cam-journey-row.is-done .cam-journey-copy strong {
            color: #102f24;
        }
        .cam-journey-state {
            padding: .42rem .72rem;
            border-radius: 999px;
            color: #8a938d;
            background: #f1eee5;
            font-size: .64rem;
            font-weight: 800;
            letter-spacing: .035em;
        }
        .cam-journey-row.is-current .cam-journey-state {
            color: #173d2f;
            background: var(--cam-gold);
        }
        .cam-journey-row.is-done .cam-journey-state {
            color: #176347;
            background: #e4f1eb;
        }
        .st-key-cam_home_journey .stButton > button {
            min-height: 3rem;
            border-radius: .65rem;
            background: #083d2d;
            box-shadow: none;
        }
        .st-key-cam_home_journey [data-testid="stCaptionContainer"] {
            color: #8a948e;
        }
        .st-key-cam_assurance_strip {
            margin: 4.5rem auto 1.6rem;
            overflow: hidden;
            border: 1px solid #e1dbce;
            border-radius: 1.1rem;
            background: #fffdf9;
        }
        .st-key-cam_assurance_strip [data-testid="stHorizontalBlock"] {
            gap: 0;
        }
        .st-key-cam_assurance_strip [data-testid="column"] + [data-testid="column"] {
            border-left: 1px solid #e1dbce;
        }
        .cam-assurance-item {
            display: flex;
            align-items: center;
            gap: 1rem;
            min-height: 6.5rem;
            padding: 1.35rem 1.7rem;
        }
        .cam-assurance-icon {
            display: grid;
            flex: 0 0 2.8rem;
            place-items: center;
            width: 2.8rem;
            height: 2.8rem;
            border-radius: .7rem;
            color: #14533e;
            background: #eee9dd;
            font-size: 1.25rem;
        }
        .cam-assurance-item strong {
            color: #163a2d;
            font-size: .9rem;
        }
        .cam-assurance-item p {
            margin: .28rem 0 0;
            color: #78857e;
            font-size: .75rem;
            line-height: 1.45;
        }
        @media (max-width: 1050px) {
            .block-container { padding-inline: 1.2rem; }
            .cam-site-header,
            .st-key-cam_top_navigation { margin-inline: -1.2rem; }
            .st-key-cam_home_experience > div > div[data-testid="stHorizontalBlock"] {
                flex-direction: column;
            }
            .st-key-cam_home_experience [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
            .st-key-cam_home_intro,
            .st-key-cam_home_journey { min-height: auto; }
            .st-key-cam_assurance_strip [data-testid="stHorizontalBlock"] {
                flex-direction: column;
            }
            .st-key-cam_assurance_strip [data-testid="column"] {
                width: 100% !important;
            }
            .st-key-cam_assurance_strip [data-testid="column"] + [data-testid="column"] {
                border-top: 1px solid #e1dbce;
                border-left: 0;
            }
        }
        @media (max-width: 760px) {
            .cam-utility-actions { gap: .35rem; }
            .cam-universe, .cam-secure { padding: .4rem .58rem; }
            .cam-home-intro-copy h1 { font-size: 2.7rem; }
            .st-key-cam_home_intro,
            .st-key-cam_home_journey { padding: 2.2rem 1.35rem; }
            .cam-hero-trust { display: grid; }
            .cam-journey-state { padding-inline: .45rem; font-size: .56rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

