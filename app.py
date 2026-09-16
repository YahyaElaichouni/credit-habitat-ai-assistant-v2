"""
Assistant IA — Crédit Habitat
Projet PFE Crédit Agricole du Maroc
===================================

Interface de démonstration permettant de tester :

1. Analyse documentaire
   Contrôle -> OCR -> Extraction -> Validation

2. Assistant IA
   Question -> Retrieval -> Contrôle du périmètre -> Réponse sourcée

Tous les appels passent par Orchestrator afin de conserver
un point d'entrée unique cohérent avec l'architecture du projet.
"""
from ocr.scan_quality import analyze_document_quality
import html
import json
import base64
import logging
import uuid
import time
import pickle
import hashlib
from pathlib import Path
from datetime import datetime
from ui.advisor_dashboard import (
    render_advisor_dashboard,
    render_advisor_sidebar,
)
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
from config.settings import settings
from database import audit
from database.customer_accounts import (
    authenticate, create_customer, delete_all_documents, delete_document,
    load_documents, load_project, save_document, save_project,
)
from extraction.schema import DOCUMENT_SCHEMAS
from ui.document_review import render_document_review
from ui.simulation import render_simulation
from ui.borrowing_capacity import render_borrowing_capacity
from copy import deepcopy
from ui.client_summary import (
    build_client_summary, render_client_summary, render_final_verification,
)

# =========================================================
# CONFIGURATION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

st.set_page_config(
    page_title="Crédit Habitat — Assistant IA",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# CACHE
# =========================================================

@st.cache_resource
def get_orchestrator():
    """Créer l'orchestrator une seule fois (caché)"""
    from agents.orchestrator import Orchestrator
    return Orchestrator()

@st.cache_data(show_spinner=False)
def get_document_quality(file_content: bytes, filename: str):
    """Éviter de recalculer la qualité à chaque rerun Streamlit."""
    return analyze_document_quality(
        content=file_content,
        filename=filename,
    )
# =========================================================
# DESIGN - STYLES AMÉLIORÉS
# =========================================================

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


def image_to_data_url(image_path):
    """Convertir une image locale en URL intégrable dans le carrousel HTML."""
    path = Path(image_path)
    if not path.is_file():
        return ""

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(path.suffix.lower(), "image/png")
    encoded_image = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded_image}"


def render_offers_carousel():
    """Afficher trois offres avec une image centrale et deux aperçus latéraux."""
    offers = [
        {
            "image": image_to_data_url("assets/offres/offre_habitat.png"),
            "title": "Financez votre projet immobilier",
            "description": (
                "Découvrez une solution de financement adaptée à votre projet "
                "et à votre situation."
            ),
        },
        {
            "image": image_to_data_url("assets/offres/offre_financement.png"),
            "title": "Une simulation simple et personnalisée",
            "description": (
                "Estimez votre mensualité et préparez votre demande de crédit "
                "en quelques étapes."
            ),
        },
        {
            "image": image_to_data_url("assets/offres/accompagnement.png"),
            "title": "Un accompagnement à chaque étape",
            "description": (
                "Notre assistant vous aide à préparer vos documents et à "
                "vérifier vos informations."
            ),
        },
    ]
    offers = [offer for offer in offers if offer["image"]]

    if len(offers) < 3:
        st.warning(
            "Le carrousel nécessite les trois images dans le dossier "
            "assets/offres."
        )
        return

    carousel_html = """
<div class="offer-carousel" id="offerCarousel">
    <div class="carousel-stage">
        <div class="slides-container" id="slidesContainer"></div>
        <button class="carousel-arrow previous" id="previousSlide"
                aria-label="Offre précédente">&#10094;</button>
        <button class="carousel-arrow next" id="nextSlide"
                aria-label="Offre suivante">&#10095;</button>
        <div class="carousel-dots" id="carouselDots"></div>
    </div>
    <div class="carousel-information">
        <div class="carousel-title" id="carouselTitle"></div>
        <div class="carousel-description" id="carouselDescription"></div>
    </div>
</div>

<style>
    * { box-sizing: border-box; }
    html, body {
        margin: 0;
        background: transparent;
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .offer-carousel { width: 100%; padding: 12px 0 4px; overflow: hidden; }
    .carousel-stage { position: relative; width: 100%; height: 455px; overflow: hidden; }
    .slides-container { position: relative; width: 100%; height: 100%; }
    .offer-slide {
        position: absolute;
        top: 25px;
        left: 50%;
        width: 76%;
        height: 390px;
        overflow: hidden;
        border-radius: 25px;
        background: #dfe9e4;
        opacity: 0;
        transform: translateX(-50%) scale(.70);
        transition: left 700ms cubic-bezier(.22, 1, .36, 1),
                    transform 700ms cubic-bezier(.22, 1, .36, 1),
                    opacity 500ms ease, filter 500ms ease;
        box-shadow: 0 16px 45px rgba(7, 59, 44, .16);
        will-change: left, transform, opacity;
    }
    .offer-slide img {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        user-select: none;
    }
    .offer-slide.is-center {
        left: 50%;
        z-index: 3;
        opacity: 1;
        transform: translateX(-50%) scale(1);
        filter: brightness(1) saturate(1);
        box-shadow: 0 25px 65px rgba(7, 59, 44, .24);
    }
    .offer-slide.is-left {
        left: 5%;
        z-index: 1;
        opacity: .55;
        transform: translateX(-50%) scale(.82);
        filter: brightness(.72) saturate(.78);
        cursor: pointer;
    }
    .offer-slide.is-right {
        left: 95%;
        z-index: 1;
        opacity: .55;
        transform: translateX(-50%) scale(.82);
        filter: brightness(.72) saturate(.78);
        cursor: pointer;
    }
    .offer-slide.is-hidden { opacity: 0; pointer-events: none; }
    .carousel-arrow {
        position: absolute;
        top: 48%;
        z-index: 10;
        width: 52px;
        height: 52px;
        padding: 0;
        border: 1px solid rgba(7, 59, 44, .12);
        border-radius: 50%;
        color: #073b2c;
        background: rgba(255, 255, 255, .94);
        font-size: 23px;
        cursor: pointer;
        transform: translateY(-50%);
        transition: transform 180ms ease, color 180ms ease,
                    background 180ms ease, box-shadow 180ms ease;
        box-shadow: 0 10px 30px rgba(7, 59, 44, .18);
    }
    .carousel-arrow:hover {
        color: #fff;
        background: #007a4d;
        transform: translateY(-50%) scale(1.08);
        box-shadow: 0 14px 35px rgba(7, 59, 44, .28);
    }
    .carousel-arrow.previous { left: 7%; }
    .carousel-arrow.next { right: 7%; }
    .carousel-dots {
        position: absolute;
        bottom: 5px;
        left: 50%;
        z-index: 10;
        display: flex;
        gap: 8px;
        transform: translateX(-50%);
    }
    .carousel-dot {
        width: 8px;
        height: 8px;
        padding: 0;
        border: 0;
        border-radius: 999px;
        background: rgba(7, 59, 44, .25);
        cursor: pointer;
        transition: width 250ms ease, background 250ms ease;
    }
    .carousel-dot.active { width: 27px; background: #007a4d; }
    .carousel-information { min-height: 92px; padding: 6px 20px 18px; text-align: center; }
    .carousel-title {
        color: #073b2c;
        font-size: 1.5rem;
        font-weight: 750;
        line-height: 1.3;
    }
    .carousel-description {
        max-width: 720px;
        margin: 8px auto 0;
        color: #52645d;
        font-size: 1rem;
        line-height: 1.55;
    }
    @media (max-width: 700px) {
        .carousel-stage { height: 345px; }
        .offer-slide { top: 20px; width: 84%; height: 285px; border-radius: 18px; }
        .offer-slide.is-left { left: 1%; }
        .offer-slide.is-right { left: 99%; }
        .carousel-arrow { width: 43px; height: 43px; font-size: 18px; }
        .carousel-arrow.previous { left: 3%; }
        .carousel-arrow.next { right: 3%; }
        .carousel-title { font-size: 1.25rem; }
        .carousel-description { font-size: .92rem; }
    }
</style>

<script>
    const offers = __OFFERS_DATA__;
    const container = document.getElementById("slidesContainer");
    const dotsContainer = document.getElementById("carouselDots");
    const title = document.getElementById("carouselTitle");
    const description = document.getElementById("carouselDescription");
    let activeSlide = 0;
    let automaticTimer;

    offers.forEach((offer, index) => {
        const slide = document.createElement("div");
        slide.className = "offer-slide";
        slide.dataset.index = index;
        const image = document.createElement("img");
        image.src = offer.image;
        image.alt = offer.title;
        image.draggable = false;
        slide.appendChild(image);
        container.appendChild(slide);

        const dot = document.createElement("button");
        dot.className = "carousel-dot";
        dot.setAttribute("aria-label", "Afficher l’offre " + (index + 1));
        dot.addEventListener("click", () => selectSlide(index));
        dotsContainer.appendChild(dot);
    });

    const slides = Array.from(document.querySelectorAll(".offer-slide"));
    const dots = Array.from(document.querySelectorAll(".carousel-dot"));

    function updateCarousel() {
        const previous = (activeSlide - 1 + offers.length) % offers.length;
        const next = (activeSlide + 1) % offers.length;
        slides.forEach((slide, index) => {
            slide.classList.remove("is-left", "is-center", "is-right", "is-hidden");
            if (index === activeSlide) slide.classList.add("is-center");
            else if (index === previous) slide.classList.add("is-left");
            else if (index === next) slide.classList.add("is-right");
            else slide.classList.add("is-hidden");
        });
        dots.forEach((dot, index) => {
            dot.classList.toggle("active", index === activeSlide);
        });
        title.textContent = offers[activeSlide].title;
        description.textContent = offers[activeSlide].description;
    }

    function restartTimer() {
        window.clearInterval(automaticTimer);
        automaticTimer = window.setInterval(showNext, 5500);
    }
    function selectSlide(index) {
        activeSlide = index;
        updateCarousel();
        restartTimer();
    }
    function showPrevious() {
        activeSlide = (activeSlide - 1 + offers.length) % offers.length;
        updateCarousel();
    }
    function showNext() {
        activeSlide = (activeSlide + 1) % offers.length;
        updateCarousel();
    }

    document.getElementById("previousSlide").addEventListener("click", () => {
        showPrevious();
        restartTimer();
    });
    document.getElementById("nextSlide").addEventListener("click", () => {
        showNext();
        restartTimer();
    });
    slides.forEach((slide) => {
        slide.addEventListener("click", () => {
            if (slide.classList.contains("is-left")) showPrevious();
            else if (slide.classList.contains("is-right")) showNext();
            restartTimer();
        });
    });

    updateCarousel();
    restartTimer();
</script>
"""

    carousel_html = carousel_html.replace(
        "__OFFERS_DATA__",
        json.dumps(offers, ensure_ascii=False),
    )
    st.iframe(carousel_html, height=585)


@st.dialog("Espace client", width="large")
def render_customer_access_dialog():
    """Regrouper la connexion et la création de compte hors de la page d'accueil."""
    login_tab, signup_tab = st.tabs(["Se connecter", "Créer un compte"])

    with login_tab:
        with st.form("customer_login_dialog", border=False):
            login_email = st.text_input(
                "Adresse e-mail",
                key="dialog_login_email",
            )
            login_password = st.text_input(
                "Mot de passe",
                type="password",
                key="dialog_login_password",
            )
            login_submit = st.form_submit_button(
                "Se connecter",
                type="primary",
                width="stretch",
            )
            if login_submit:
                customer = authenticate(login_email, login_password)
                if customer is None:
                    st.error("Adresse e-mail ou mot de passe incorrect.")
                else:
                    st.session_state.customer_profile = {
                        "prenom": customer["first_name"],
                        "nom": customer["last_name"],
                        "email": customer["email"],
                        "telephone": customer["phone"],
                    }
                    st.session_state.current_client_id = customer["id"]
                    st.session_state.documents = load_documents(customer["id"])
                    st.session_state.account_created = True
                    st.session_state.page = "Accueil"
                    st.rerun()

    with signup_tab:
        with st.form("customer_signup_dialog", border=False):
            left, right = st.columns(2)
            prenom = left.text_input("Prénom *", key="dialog_signup_first_name")
            nom = right.text_input("Nom *", key="dialog_signup_last_name")
            email = left.text_input("Adresse e-mail *", key="dialog_signup_email")
            telephone = right.text_input("Téléphone *", key="dialog_signup_phone")
            password = left.text_input(
                "Mot de passe *",
                type="password",
                key="dialog_signup_password",
            )
            confirmation = right.text_input(
                "Confirmer le mot de passe *",
                type="password",
                key="dialog_signup_password_confirmation",
            )
            consent = st.checkbox(
                "J'accepte que mes informations soient utilisées pour préparer cette simulation.",
                key="dialog_signup_consent",
            )
            submitted = st.form_submit_button(
                "Créer mon compte",
                type="primary",
                width="stretch",
            )
            if submitted:
                if password != confirmation:
                    st.error("Les deux mots de passe ne correspondent pas.")
                elif not consent:
                    st.error("Votre accord est nécessaire pour poursuivre.")
                else:
                    try:
                        customer = create_customer(
                            email,
                            password,
                            prenom,
                            nom,
                            telephone,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.customer_profile = {
                            "prenom": customer["first_name"],
                            "nom": customer["last_name"],
                            "email": customer["email"],
                            "telephone": customer["phone"],
                        }
                        st.session_state.current_client_id = customer["id"]
                        st.session_state.documents = load_documents(customer["id"])
                        st.session_state.account_created = True
                        st.session_state.page = "Accueil"
                        st.rerun()


def render_header():
    """Afficher un en-tête inspiré de l'identité institutionnelle du GCAM."""
    page_labels = {
        "Accueil": "Mon projet habitat",
        "Extraction": "Mes justificatifs",
        "Verification": "Vérification des informations",
        "Estimation": "Estimation rapide",
        "Simulation": "Ma simulation",
    }
    current_page = page_labels.get(st.session_state.page, "Crédit Habitat")
    logo_url = image_to_data_url("assets/logo_ca.jpg")
    st.markdown(
        """
        <header class="cam-site-header">
            <div class="cam-utility-bar">
                <span class="cam-corporate">Groupe Crédit Agricole du Maroc</span>
                <div class="cam-utility-actions">
                    <span class="cam-universe">UNIVERS CAM</span>
                    <span class="cam-secure">&#128274; PARCOURS SÉCURISÉ</span>
                </div>
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )

    if logo_url:
        st.markdown(
            f"""
            <style>
            .st-key-top_nav_logo button {{
                background-image: url("{logo_url}") !important;
                background-position: left .85rem center !important;
                background-size: 54px auto !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    account_ready = bool(st.session_state.account_created)
    profile = st.session_state.get("customer_profile", {})
    initials = "".join(
        str(value).strip()[:1].upper()
        for value in (profile.get("prenom"), profile.get("nom"))
        if value
    ) or "CL"
    documents = current_client_documents() if account_ready else {}
    required_types = {"carte_identite", "bulletin", "releve"}
    documents_ready = account_ready and required_types.issubset(
        reviewed_document_types(documents)
    )
    dossier_complete = False
    if account_ready:
        _, _, dossier_complete, _ = dossier_readiness()

    with st.container(key="cam_top_navigation"):
        (
            nav_logo,
            nav_project,
            nav_docs,
            nav_check,
            nav_sim,
            nav_estimate,
            nav_space,
        ) = st.columns(
            [1.55, .95, 1.05, 1.15, .95, 1, .9],
            gap="small",
        )
        with nav_logo:
            if st.button(
                "Crédit Agricole du Maroc",
                width="stretch",
                key="top_nav_logo",
                help="Retour à l'accueil",
                disabled=st.session_state.processing,
            ):
                _go_to("Accueil")
                st.rerun()
        with nav_project:
            if st.button(
                "1  Mon projet",
                width="stretch",
                type="primary" if st.session_state.page == "Accueil" else "secondary",
                key="top_nav_project",
                disabled=st.session_state.processing,
            ):
                _go_to("Accueil")
                st.rerun()
        with nav_docs:
            if st.button(
                "2  Justificatifs",
                width="stretch",
                type="primary" if st.session_state.page == "Extraction" else "secondary",
                key="top_nav_documents",
                disabled=st.session_state.processing or not account_ready,
            ):
                _go_to("Extraction")
                st.rerun()
        with nav_check:
            if st.button(
                "3  Vérification",
                width="stretch",
                type="primary" if st.session_state.page == "Verification" else "secondary",
                key="top_nav_verification",
                disabled=st.session_state.processing or not documents_ready,
            ):
                _go_to("Verification")
                st.rerun()
        with nav_sim:
            if st.button(
                "4  Simulation",
                width="stretch",
                type="primary" if st.session_state.page == "Simulation" else "secondary",
                key="top_nav_simulation",
                disabled=st.session_state.processing or not dossier_complete,
            ):
                _go_to("Simulation")
                st.rerun()
        with nav_estimate:
            if st.button(
                "5  Estimation",
                width="stretch",
                type="primary" if st.session_state.page == "Estimation" else "secondary",
                key="top_nav_estimation",
                disabled=st.session_state.processing,
            ):
                _go_to("Estimation")
                st.rerun()
        with nav_space:
            with st.popover(f"{initials}  Mon espace", width="stretch"):
                if account_ready:
                    profile = st.session_state.customer_profile
                    display_name = " ".join(
                        filter(None, (profile.get("prenom"), profile.get("nom")))
                    ).strip()
                    safe_name = html.escape(display_name or "Mon compte")
                    safe_email = html.escape(str(profile.get("email", "")))
                    st.markdown(
                        f"""
                        <div class="cam-space-profile">
                            <div class="cam-space-name">{safe_name}</div>
                            <div class="cam-space-email">{safe_email}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    try:
                        saved_project = (
                            load_project(st.session_state.current_client_id) or {}
                        )
                    except Exception:
                        saved_project = {}
                    completed_steps = sum(
                        (bool(saved_project), documents_ready, dossier_complete, dossier_complete)
                    )
                    progress_percent = int(completed_steps / 4 * 100)
                    st.markdown(
                        f'<div class="cam-space-progress">Avancement du dossier : '
                        f'<strong>{progress_percent} %</strong></div>',
                        unsafe_allow_html=True,
                    )
                    st.progress(progress_percent / 100)
                else:
                    st.caption(
                        "Connectez-vous pour sauvegarder et reprendre votre dossier."
                    )
                    if st.button(
                        "Espace client",
                        icon=":material/account_circle:",
                        type="primary",
                        width="stretch",
                        key="top_nav_customer_access",
                    ):
                        render_customer_access_dialog()

                if st.button(
                    "Demander à Nour",
                    icon=":material/chat:",
                    width="stretch",
                    key="top_nav_nour",
                ):
                    st.session_state.assistant_open = True
                    st.rerun()

                st.markdown("**🛡️ Confidentialité**")
                st.caption(
                    "Vos justificatifs servent uniquement à préparer votre simulation."
                )
                st.caption(
                    "Vous gardez le contrôle sur les informations enregistrées."
                )

                if st.button(
                    "Espace conseiller",
                    icon=":material/admin_panel_settings:",
                    width="stretch",
                    key="top_nav_advisor",
                ):
                    st.session_state.page = "Conseiller"
                    st.rerun()

                if account_ready and st.button(
                    "Se déconnecter",
                    icon=":material/logout:",
                    width="stretch",
                    key="top_nav_logout",
                ):
                    for key in (
                        "documents", "current_doc_id", "confirmed_fields", "last_result",
                        "chat_history", "credit_profile", "customer_profile",
                        "compromis_skipped",
                    ):
                        st.session_state.pop(key, None)
                    st.session_state.account_created = False
                    st.session_state.current_client_id = None
                    st.session_state.page = "Accueil"
                    st.rerun()

    st.markdown(
        f"""
        <div class="cam-breadcrumb">
            Accueil &nbsp;&gt;&nbsp; <strong>{html.escape(current_page)}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cam_hero(eyebrow, title, text, badge):
    """Afficher l'accueil principal et l'avancement réel du dossier."""
    account_ready = bool(st.session_state.account_created)
    project_ready = False
    documents_ready = False
    dossier_complete = False

    if account_ready:
        try:
            project_ready = bool(load_project(st.session_state.current_client_id))
        except Exception:
            project_ready = False
        documents = current_client_documents()
        required_types = {"carte_identite", "bulletin", "releve"}
        documents_ready = required_types.issubset(reviewed_document_types(documents))
        try:
            _, _, dossier_complete, _ = dossier_readiness()
        except Exception:
            dossier_complete = False

    # La quatrième étape devient disponible lorsque le dossier est complet.
    # Elle reste l'étape active tant que le client se trouve sur l'accueil.
    completed = [
        project_ready,
        documents_ready,
        dossier_complete,
        False,
    ]
    active_index = next(
        (index for index, is_done in enumerate(completed) if not is_done),
        3,
    )
    journey_steps = (
        ("Décrire le projet", "Type de bien, montant et apport"),
        ("Ajouter les justificatifs", "Identité, revenus et relevé bancaire"),
        ("Vérifier les informations", "Correction et validation avant simulation"),
        ("Comparer les simulations", "Durées, mensualités et capacité d'emprunt"),
    )
    journey_rows = []
    for index, (label, description) in enumerate(journey_steps):
        if completed[index]:
            row_class = "is-done"
            state = "TERMINÉ"
        elif index == active_index:
            row_class = "is-current"
            state = "EN COURS" if account_ready else "COMMENCER"
        else:
            row_class = ""
            state = "À FAIRE"
        journey_rows.append(
            f"""
            <div class="cam-journey-row {row_class}">
                <span class="cam-journey-number">{index + 1}</span>
                <span class="cam-journey-copy">
                    <strong>{html.escape(label)}</strong>
                    <small>{html.escape(description)}</small>
                </span>
                <span class="cam-journey-state">{state}</span>
            </div>
            """
        )
    journey_html = "".join(journey_rows)
    current_step = min(sum(completed) + 1, 4)
    progress_percent = current_step * 25

    if not account_ready:
        primary_label = "Démarrer le parcours"
    elif not project_ready:
        primary_label = "Décrire mon projet"
    elif not documents_ready:
        primary_label = "Ajouter mes justificatifs"
    elif not dossier_complete:
        primary_label = "Vérifier mes informations"
    else:
        primary_label = "Voir ma simulation"

    def continue_journey():
        if not account_ready:
            render_customer_access_dialog()
        elif not project_ready:
            st.session_state.editing_home_project = True
            st.rerun()
        elif not documents_ready:
            _go_to("Extraction")
            st.rerun()
        elif not dossier_complete:
            _go_to("Verification")
            st.rerun()
        else:
            _go_to("Simulation")
            st.rerun()

    with st.container(key="cam_home_experience"):
        intro_column, journey_column = st.columns([1.35, 1], gap=None)

        with intro_column:
            with st.container(key="cam_home_intro", height="stretch"):
                st.markdown(
                    f"""
                    <div class="cam-home-intro-copy">
                        <div class="ca-eyebrow"><span></span>{html.escape(str(eyebrow))}</div>
                        <h1>{html.escape(str(title))}</h1>
                        <p>{html.escape(str(text))}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                primary_action, example_action = st.columns([1.25, 1], gap="small")
                with primary_action:
                    if st.button(
                        primary_label,
                        icon=":material/arrow_forward:",
                        type="primary",
                        width="stretch",
                        key="cam_home_primary_action",
                        disabled=st.session_state.processing,
                    ):
                        continue_journey()
                with example_action:
                    if st.button(
                        "Faire une estimation",
                        width="stretch",
                        key="cam_home_example_action",
                        disabled=st.session_state.processing,
                    ):
                        _go_to("Estimation")
                        st.rerun()
                st.markdown(
                    """
                    <div class="cam-hero-trust">
                        <span>♢&nbsp; Données protégées</span>
                        <span>✓&nbsp; Validation par vos soins</span>
                        <span>◷&nbsp; Estimation non contractuelle</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with journey_column:
            with st.container(key="cam_home_journey", height="stretch"):
                st.markdown(
                    f"""
                    <div class="cam-journey-kicker">VOTRE DEMANDE</div>
                    <div class="cam-journey-title">Un parcours guidé, étape par étape</div>
                    <div class="cam-journey-subtitle">Étape {current_step} sur 4 · progression enregistrée automatiquement</div>
                    <div class="cam-journey-progress" role="progressbar" aria-valuenow="{progress_percent}" aria-valuemin="0" aria-valuemax="100">
                        <span style="width:{progress_percent}%"></span>
                    </div>
                    <div class="cam-journey-list">{journey_html}</div>
                    """,
                    unsafe_allow_html=True,
                )
                footer_info, footer_action = st.columns([1.1, .9], vertical_alignment="center")
                with footer_info:
                    st.caption(f"Progression {current_step}/4 étapes")
                with footer_action:
                    if st.button(
                        "Continuer",
                        icon=":material/arrow_forward:",
                        type="primary",
                        width="stretch",
                        key="cam_home_continue_action",
                        disabled=st.session_state.processing,
                    ):
                        continue_journey()


def render_home_assurance_strip():
    """Afficher les trois garanties principales sous le parcours d'accueil."""
    items = (
        ("⌑", "Données traitées localement", "Vos documents restent dans l'environnement de démonstration."),
        ("◷", "Reprenez à tout moment", "Votre projet et votre progression sont enregistrés."),
        ("⌂", "Simulation immédiate", "Comparez plusieurs scénarios de financement sans engagement."),
    )
    with st.container(key="cam_assurance_strip"):
        columns = st.columns(3, gap=None)
        for column, (icon, title, description) in zip(columns, items):
            with column:
                st.markdown(
                    f"""
                    <article class="cam-assurance-item">
                        <div class="cam-assurance-icon">{icon}</div>
                        <div>
                            <strong>{html.escape(title)}</strong>
                            <p>{html.escape(description)}</p>
                        </div>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )


def render_article_card(icon, title, text, tag):
    """Afficher une carte éditoriale compacte sur l'accueil."""
    st.markdown(
        f"""
        <article class="ca-article">
            <div class="icon">{icon}</div>
            <h3>{title}</h3>
            <p>{text}</p>
            <span class="ca-tag">{tag}</span>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _go_to(page):
    st.session_state.page = page


def current_client_documents():
    return {
        doc_id: document for doc_id, document in st.session_state.documents.items()
        if document.get("client_id") == st.session_state.current_client_id
    }


DOCUMENT_JOURNEY = (
    {
        "type": "carte_identite",
        "title": "Carte d'identité",
        "instruction": "Ajoutez le recto et le verso de votre carte d'identité.",
        "optional": False,
    },
    {
        "type": "bulletin",
        "title": "Bulletin de paie",
        "instruction": "Ajoutez votre bulletin de paie le plus récent.",
        "optional": False,
    },
    {
        "type": "releve",
        "title": "Relevé bancaire",
        "instruction": "Ajoutez un relevé bancaire récent et lisible.",
        "optional": False,
    },
    {
        "type": "compromis",
        "title": "Compromis de vente",
        "instruction": "Ajoutez votre compromis si vous l'avez déjà signé.",
        "optional": True,
    },
)


def completed_document_types(documents=None):
    """Retourner les types dont l'analyse est terminée pour le client connecté."""
    documents = documents if documents is not None else current_client_documents()
    return {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
    }


def reviewed_document_types(documents=None):
    """Retourner les types explicitement validés par l'utilisateur."""
    documents = documents if documents is not None else current_client_documents()
    return {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
        and document.get("journey_reviewed") is True
    }


def required_documents_ready(documents=None):
    documents = documents if documents is not None else current_client_documents()
    required_types = {"carte_identite", "bulletin", "releve"}
    return (
        required_types.issubset(completed_document_types(documents))
        and required_types.issubset(reviewed_document_types(documents))
    )


def credit_journey_step(documents=None):
    """Déterminer automatiquement la prochaine étape du parcours de crédit."""
    documents = documents if documents is not None else current_client_documents()
    completed_types = completed_document_types(documents)
    reviewed_types = reviewed_document_types(documents)

    for index, document_step in enumerate(DOCUMENT_JOURNEY[:3]):
        document_type = document_step["type"]
        if document_type not in completed_types or document_type not in reviewed_types:
            return index

    if not st.session_state.get("compromis_skipped", False):
        if "compromis" not in completed_types or "compromis" not in reviewed_types:
            return 3

    _, information_ready = build_client_summary(documents)
    return 5 if information_ready and st.session_state.page == "Simulation" else 4


def render_credit_journey(active_step):
    """Afficher les six étapes du parcours dans un format court et lisible."""
    labels = (
        "Identité",
        "Bulletin",
        "Relevé",
        "Compromis",
        "Vérification",
        "Simulation",
    )
    st.progress(min(active_step, 5) / 5)
    columns = st.columns(len(labels), gap="small")

    for index, (column, label) in enumerate(zip(columns, labels)):
        if index < active_step:
            icon = "✅"
        elif index == active_step:
            icon = "●"
        else:
            icon = "○"

        with column:
            st.markdown(f"**{icon} {index + 1}**")
            st.caption(label)


def render_guided_document_review(document_id, document, journey_step, advisor_id):
    """Afficher le contrôle humain obligatoire avant l'étape suivante."""
    result = document.get("result") or {}
    control_result = result.get("control_result", {})

    st.subheader(f"Informations détectées — {document.get('filename', 'Document')}")
    st.caption(
        "Relisez les informations, corrigez les valeurs nécessaires, puis utilisez "
        "le bouton Continuer en bas de cette étape."
    )

    if not control_result.get("valid", False):
        st.error(
            f"Document rejeté : {control_result.get('reason', 'raison inconnue')}"
        )
        if st.button(
            "Supprimer et déposer un autre document",
            icon=":material/delete:",
            width="stretch",
            key=f"guided_delete_invalid_{document_id}",
        ):
            delete_one_document_dialog(document_id)
        return

    security = result.get("extraction_security", {})
    if security.get("suspicious"):
        st.warning(
            "Certaines informations du document demandent une vérification attentive."
        )

    validation_result = result.get("validation_result") or {}
    fields = validation_result.get("fields", {})
    if not fields:
        st.error("Aucune information exploitable n'a été extraite de ce document.")
        return

    confirmations = deepcopy(document.get("confirmed_fields") or {})
    submitted = render_document_review(
        result, document["type"], document_id, advisor_id,
        st.session_state.session_id, confirmations,
    )
    if submitted:
        updated = dict(document, confirmed_fields=confirmations, journey_reviewed=True)
        try:
            save_document(st.session_state.current_client_id, document_id, updated)
        except Exception:
            st.error("La sauvegarde a échoué. Vos saisies sont conservées ; réessayez.")
            return
        document.update(updated)
        st.session_state.current_doc_id = None
        st.session_state.last_result = None
        st.session_state.confirmed_fields = {}
        st.session_state.journey_notice = "Vos informations sont enregistrées."
        st.rerun()


def _remove_uploaded_files(paths):
    """Supprime uniquement des fichiers situés dans le répertoire d'upload."""
    upload_root = Path("data/uploads").resolve()
    failures = []
    for raw_path in set(filter(None, paths)):
        try:
            candidate = Path(raw_path).resolve()
            if not candidate.is_relative_to(upload_root):
                failures.append(Path(raw_path).name)
                continue
            if candidate.is_file():
                candidate.unlink()
        except (OSError, RuntimeError):
            failures.append(Path(raw_path).name)
    return failures


def _clear_document_session(documents):
    """Retire l'état lié aux justificatifs sans déconnecter le client."""
    document_ids = tuple(documents)
    client_id = st.session_state.current_client_id
    for key in list(st.session_state):
        key_text = str(key)
        if any(document_id in key_text for document_id in document_ids):
            st.session_state.pop(key, None)
        elif key_text.startswith(f"declared_{client_id}_"):
            st.session_state.pop(key, None)
        elif key_text.startswith((f"verification_table_{client_id}",
                                  f"verification_checked_{client_id}")):
            st.session_state.pop(key, None)
    for key, default in (
        ("current_doc_id", None),
        ("confirmed_fields", {}),
        ("last_result", None),
    ):
        st.session_state[key] = default


@st.dialog("Recommencer avec de nouveaux justificatifs")
def reset_documents_dialog():
    """Demande une confirmation avant la réinitialisation du dossier documentaire."""
    documents = current_client_documents()
    st.warning(
        "Cette action supprimera tous vos justificatifs ainsi que les informations "
        "extraites, corrigées et confirmées à partir de ces documents."
    )
    st.info("Votre compte client et les informations de votre projet immobilier seront conservés.")
    confirmed = st.checkbox(
        "Je comprends que les justificatifs devront être déposés et vérifiés de nouveau",
        key="confirm_reset_all_documents",
    )
    if st.button(
        "Supprimer les justificatifs",
        icon=":material/delete_sweep:",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key="reset_all_documents_confirm",
    ):
        try:
            stored_paths = delete_all_documents(st.session_state.current_client_id)
        except Exception as exc:
            st.error(f"Réinitialisation impossible : {exc}")
            return
        session_paths = [document.get("document_path") for document in documents.values()]
        failures = _remove_uploaded_files(stored_paths + session_paths)
        _clear_document_session(documents)
        st.session_state.compromis_skipped = False
        for document_id in documents:
            st.session_state.documents.pop(document_id, None)
        audit.log_event(
            "client_documents_reset",
            advisor_id=f"client_portal_{st.session_state.session_id[:8]}",
            session_id=st.session_state.session_id,
            decision="confirme_par_client",
            details={"documents_supprimes": len(documents), "fichiers_non_supprimes": failures},
        )
        st.session_state.documents_reset_notice = (
            "Vos anciens justificatifs et leurs informations ont été supprimés. "
            "Vous pouvez déposer les nouveaux documents."
        )
        st.rerun()


@st.dialog("Supprimer ce justificatif")
def delete_one_document_dialog(document_id):
    document = st.session_state.documents.get(document_id)
    if not document or document.get("client_id") != st.session_state.current_client_id:
        st.error("Ce justificatif n'est plus disponible.")
        return
    st.warning(
        f"Le justificatif « {document.get('filename') or 'Document'} » et toutes les "
        "informations confirmées depuis cette pièce seront supprimés."
    )
    confirmed = st.checkbox(
        "Je confirme la suppression de ce justificatif",
        key=f"confirm_delete_document_{document_id}",
    )
    if st.button(
        "Supprimer définitivement",
        icon=":material/delete:",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key=f"delete_document_confirm_{document_id}",
    ):
        try:
            delete_document(st.session_state.current_client_id, document_id)
        except Exception as exc:
            st.error(f"Suppression impossible : {exc}")
            return
        failures = _remove_uploaded_files([document.get("document_path")])
        for key in list(st.session_state):
            if document_id in str(key):
                st.session_state.pop(key, None)
        st.session_state.documents.pop(document_id, None)
        if st.session_state.get("current_doc_id") == document_id:
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.session_state.confirmed_fields = {}
        st.session_state.pop(f"verification_table_{st.session_state.current_client_id}", None)
        st.session_state.pop(f"verification_checked_{st.session_state.current_client_id}", None)
        audit.log_event(
            "client_document_deleted",
            advisor_id=f"client_portal_{st.session_state.session_id[:8]}",
            session_id=st.session_state.session_id,
            document_path=document.get("document_path"),
            document_type=document.get("type"),
            decision="confirme_par_client",
            details={"fichier_non_supprime": failures},
        )
        st.session_state.documents_reset_notice = "Le justificatif a été supprimé."
        st.rerun()


def _confirmed_candidates(documents, field):
    candidates = []
    for document_id, document in documents.items():
        record = (document.get("confirmed_fields") or {}).get(field)
        if not isinstance(record, dict):
            continue
        if record.get("document_id") != document_id:
            continue
        if record.get("status") not in ("confirme", "corrige"):
            continue
        if record.get("value") is None:
            continue
        candidates.append({
            "document_id": document_id,
            "filename": document.get("filename") or "Document",
            "value": record["value"],
            "record": record,
        })
    return candidates


def render_conflict_resolution(documents, rows, advisor_id):
    """Laisse le client choisir explicitement la source à conserver."""
    conflicts = [row for row in rows if row.get("Statut") == "Conflit"]
    if not conflicts:
        return
    st.subheader("Résoudre les informations contradictoires")
    st.warning(
        "Deux justificatifs contiennent des valeurs différentes. Choisissez la valeur "
        "qui correspond à votre situation actuelle après consultation des documents."
    )
    for row in conflicts:
        field = row["field"]
        candidates = _confirmed_candidates(documents, field)
        if len(candidates) < 2:
            continue
        with st.container(border=True):
            st.markdown(f"**{row['Champ']}**")
            st.dataframe(
                [{
                    "Valeur": str(candidate["value"]),
                    "Justificatif": candidate["filename"],
                    "Page": str((candidate["record"].get("source") or {}).get("page") or "—"),
                    "Extrait": str((candidate["record"].get("source") or {}).get("quote") or "—"),
                } for candidate in candidates],
                hide_index=True,
                width="stretch",
            )
            choice = st.selectbox(
                "Valeur à conserver",
                options=range(len(candidates)),
                format_func=lambda index: (
                    f"{candidates[index]['value']} — {candidates[index]['filename']}"
                ),
                key=f"conflict_choice_{field}",
            )
            checked = st.checkbox(
                "J'ai comparé les justificatifs et je confirme ce choix",
                key=f"conflict_checked_{field}",
            )
            if st.button(
                "Conserver cette valeur",
                icon=":material/check_circle:",
                type="primary",
                disabled=not checked,
                key=f"resolve_conflict_{field}",
            ):
                selected = candidates[choice]
                discarded = []
                for candidate in candidates:
                    if candidate["document_id"] == selected["document_id"]:
                        continue
                    document = documents[candidate["document_id"]]
                    (document.get("confirmed_fields") or {}).pop(field, None)
                    save_document(
                        st.session_state.current_client_id,
                        candidate["document_id"],
                        document,
                    )
                    discarded.append({
                        "document": candidate["filename"],
                        "value": candidate["value"],
                    })
                audit.log_event(
                    "client_conflict_resolved",
                    advisor_id=advisor_id,
                    session_id=st.session_state.session_id,
                    document_path=selected["filename"],
                    field_name=field,
                    value=selected["value"],
                    decision="valeur_conservee_par_client",
                    details={"valeurs_ecartees": discarded},
                )
                st.toast("Conflit résolu et choix sauvegardé.", icon=":material/check_circle:")
                st.rerun()


def dossier_readiness():
    """État métier réel utilisé pour verrouiller/déverrouiller la simulation."""
    documents = current_client_documents()
    rows, business_complete = build_client_summary(documents) if documents else ([], False)
    missing = [row["Champ"] for row in rows if row["Statut"] in ("Manquant", "Conflit")]
    required_documents = {
        "carte_identite": "Carte d'identité",
        "bulletin": "Bulletin de paie",
        "releve": "Relevé bancaire",
    }
    available_types = {
        document.get("type") for document in documents.values()
        if document.get("status") == "completed"
    }
    missing.extend(label for doc_type, label in required_documents.items()
                   if doc_type not in available_types)
    reviewed_types = reviewed_document_types(documents)
    missing.extend(
        f"Vérification du document : {label}"
        for doc_type, label in required_documents.items()
        if doc_type not in reviewed_types
    )
    return documents, rows, business_complete and not missing, missing


def render_application_sidebar():
    """Navigation bancaire courte, guidée et compréhensible sans jargon."""
    account_ready = bool(st.session_state.account_created)
    documents = current_client_documents() if account_ready else {}
    completed_types = {
        document.get("type") for document in documents.values()
        if document.get("status") == "completed"
    }
    missing_document_count = len(
        {"carte_identite", "bulletin", "releve"} - completed_types
    )
    required_types = {"carte_identite", "bulletin", "releve"}
    reviewed_types = reviewed_document_types(documents)
    documents_ready = (
        missing_document_count == 0
        and required_types.issubset(reviewed_types)
    )

    saved_project = {}
    if account_ready:
        try:
            saved_project = load_project(st.session_state.current_client_id) or {}
        except Exception:
            saved_project = {}
    project_ready = bool(saved_project)

    dossier_complete = False
    if account_ready:
        _, _, dossier_complete, _ = dossier_readiness()
    completed_steps = sum((project_ready, documents_ready, dossier_complete, dossier_complete))
    progress_percent = int(completed_steps / 4 * 100)

    logo = Path("assets/logo_ca.jpg")
    with st.container(key="sidebar_brand"):
        logo_column, title_column = st.columns([1, 2.8], vertical_alignment="center")
        with logo_column:
            if logo.is_file():
                st.image(str(logo), width=58)
            else:
                st.markdown(":material/account_balance:")
        with title_column:
            st.markdown("**Crédit Agricole  \\\ndu Maroc**")

    with st.container(key="sidebar_intro"):
        st.markdown("## Crédit Habitat")
        st.caption("Votre projet, étape par étape")

    with st.container(key="sidebar_progress"):
        if not account_ready:
            next_step = "Connectez-vous pour préparer votre dossier."
        elif not project_ready:
            next_step = "Prochaine étape : renseigner votre projet."
        elif not documents_ready:
            next_step = "Prochaine étape : ajouter vos justificatifs."
        elif not dossier_complete:
            next_step = "Prochaine étape : vérifier vos informations."
        else:
            next_step = "Votre simulation est prête."
        st.markdown(
            f"""
            <div class="sidebar-progress-head">
                <span>Avancement du dossier</span>
                <span>{progress_percent} %</span>
            </div>
            <div class="sidebar-progress-track">
                <div class="sidebar-progress-fill" style="width:{progress_percent}%"></div>
            </div>
            <div class="sidebar-progress-copy">{next_step}</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sidebar-section-label">VOTRE PARCOURS</div>', unsafe_allow_html=True)
    with st.container(key="sidebar_nav"):
        if st.button(
            "01  Mon projet",
            icon=":material/home:",
            width="stretch",
            type="primary" if st.session_state.page == "Accueil" else "secondary",
            disabled=st.session_state.processing,
            key="sidebar_overview",
        ):
            _go_to("Accueil")
            st.rerun()

        

        if st.button(
            "02  Mes justificatifs", icon=":material/description:", width="stretch",
            type="primary" if st.session_state.page == "Extraction" else "secondary",
            disabled=st.session_state.processing or not account_ready,
            key="sidebar_documents",
        ):
            _go_to("Extraction")
            st.rerun()
        if missing_document_count:
            documents_hint = f"{missing_document_count} document{'s' if missing_document_count > 1 else ''} à ajouter"
        elif documents_ready:
            documents_hint = "Documents vérifiés"
        else:
            documents_hint = "Informations à vérifier"
        st.markdown(f'<div class="sidebar-step-hint">{documents_hint}</div>', unsafe_allow_html=True)

        if st.button(
            "03  Vérifier mes informations", icon=":material/fact_check:", width="stretch",
            type="primary" if st.session_state.page == "Verification" else "secondary",
            disabled=st.session_state.processing or not documents_ready,
            key="sidebar_verification",
        ):
            _go_to("Verification")
            st.rerun()
        verification_hint = "Terminé" if dossier_complete else (
            "Prêt à vérifier" if documents_ready else "Disponible après les documents"
        )
        st.markdown(f'<div class="sidebar-step-hint">{verification_hint}</div>', unsafe_allow_html=True)

        if st.button(
            "04  Ma simulation", icon=":material/calculate:", width="stretch",
            type="primary" if st.session_state.page == "Simulation" else "secondary",
            disabled=st.session_state.processing or not dossier_complete,
            key="sidebar_simulation",
        ):
            _go_to("Simulation")
            st.rerun()
        simulation_hint = "Disponible" if dossier_complete else "Disponible après vérification"
        st.markdown(f'<div class="sidebar-step-hint">{simulation_hint}</div>', unsafe_allow_html=True)

    if st.button(
        "Estimation rapide",
        key="sidebar_quick",
        width="stretch",
        icon=":material/calculate:",
        disabled=st.session_state.processing,
    ):
        _go_to("Estimation")
        st.rerun()

    with st.container(key="sidebar_support"):
        if st.button(
            "Une question ? Demandez à Nour",
            icon=":material/help:",
            width="stretch",
            key="sidebar_help",
        ):
            st.session_state.assistant_open = True
            st.rerun()
        with st.expander("Confidentialité", icon=":material/shield:"):
            st.caption("Vos justificatifs servent uniquement à préparer votre simulation.")
            st.caption("Vous gardez le contrôle sur les informations enregistrées.")
        if st.button(
            "Espace conseiller",
            icon=":material/admin_panel_settings:",
            width="stretch",
            key="open_advisor_space",
        ):
            st.session_state.page = "Conseiller"
            st.rerun()
    if account_ready:
        profile = st.session_state.customer_profile
        display_name = " ".join(filter(None, (profile.get("prenom"), profile.get("nom")))).strip()
        initials = "".join(part[:1].upper() for part in display_name.split()[:2]) or "CL"
        safe_display_name = html.escape(display_name or "Mon compte")
        safe_email = html.escape(str(profile.get("email", "")))
        with st.container(key="sidebar_profile"):
            st.markdown(
                f"""
                <div class="sidebar-user-card">
                    <div class="sidebar-user-name">{initials} · {safe_display_name}</div>
                    <div class="sidebar-user-email">{safe_email}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            logout = st.button(
                "Se déconnecter",
                icon=":material/logout:",
                width="stretch",
                key="sidebar_logout",
            )
            if logout:
                for key in (
                    "documents", "current_doc_id", "confirmed_fields", "last_result",
                    "chat_history", "credit_profile", "customer_profile",
                    "compromis_skipped",
                ):
                    st.session_state.pop(key, None)
                st.session_state.account_created = False
                st.session_state.current_client_id = None
                st.session_state.page = "Accueil"
                st.rerun()


def apply_assistant_result(result):
    """Mémoriser le profil et préremplir l'estimation rapide."""
    profile = result.get("profile")
    if not isinstance(profile, dict):
        return

    st.session_state.credit_profile = profile
    project = dict(st.session_state.get("quick_project", {}))
    project_mapping = {
        "prix_bien": "purchase_price",
        "apport_personnel": "contribution",
        "duree_souhaitee_annees": "duration_years",
    }
    widget_mapping = {
        "prix_bien": ("quick_price",),
        "apport_personnel": (
            "quick_contribution",
            "quick_capacity_contribution",
        ),
        "duree_souhaitee_annees": (
            "quick_years",
            "quick_capacity_years",
        ),
        "revenu_mensuel_net": ("quick_capacity_income",),
        "charges_mensuelles": ("quick_capacity_charges",),
    }

    for field in result.get("profile_updates", {}):
        if field in project_mapping and profile.get(field) is not None:
            project[project_mapping[field]] = profile[field]
        for widget_key in widget_mapping.get(field, ()):
            st.session_state.pop(widget_key, None)

    st.session_state.quick_project = project


def render_assistant_dock(advisor_id):
    """Afficher un assistant flottant lisible sur ordinateur et mobile."""
    robot_path = Path(__file__).resolve().parent / "assets" / "assistant_habitat_robot.png"
    assistant_avatar = str(robot_path) if robot_path.exists() else ":material/smart_toy:"

    if not st.session_state.assistant_open:
        with st.container(key="assistant_launcher"):
            if st.button(
                "Nour · Assistant habitat",
                icon=":material/smart_toy:",
                key="open_assistant_dock",
                width="stretch",
                help="Ouvrir votre assistant virtuel",
            ):
                st.session_state.assistant_open = True
                st.rerun()
        return

    with st.container(key="assistant_dock", border=True):
        avatar_col, title_col, close_col = st.columns(
            [1.2, 5.6, 1],
            vertical_alignment="center",
        )
        with avatar_col:
            if robot_path.exists():
                st.image(str(robot_path), width=54)
            else:
                st.markdown(":material/smart_toy:")
        with title_col:
            st.markdown("**Nour, votre assistant habitat**")
            st.caption("En ligne · Je vous accompagne étape par étape")
        with close_col:
            if st.button(
                "×",
                key="assistant_close",
                help="Fermer l’assistant",
                width="content",
            ):
                st.session_state.assistant_open = False
                st.rerun()

        history = st.session_state.chat_history[-6:]
        if not history:
            st.write(
                "Bonjour ! Je vais vous accompagner étape par étape. "
                "Vous pouvez commencer par me parler de votre profession "
                "et de votre projet immobilier."
            )
            suggestions = {
                "Décrire ma situation": (
                    "Je souhaite préparer mon projet de crédit habitat."
                ),
                "Documents à préparer": "Quels documents dois-je préparer pour ma simulation ?",
                "Estimer ma mensualité": "Comment est calculée la mensualité de mon crédit habitat ?",
            }
            selected = st.pills(
                "Questions suggérées",
                list(suggestions),
                label_visibility="collapsed",
                key="assistant_dock_suggestions",
            )
            suggested_question = suggestions.get(selected)
        else:
            suggested_question = None
            with st.container(height=320, border=False):
                for exchange in history:
                    with st.chat_message("user", avatar=":material/person:"):
                        st.write(exchange["question"])
                    with st.chat_message("assistant", avatar=assistant_avatar):
                        st.write(exchange["answer"])

        question = st.chat_input(
            "Posez votre question…",
            key="assistant_dock_input",
            disabled=st.session_state.processing,
            submit_mode="disable",
        )
        question = question or suggested_question
        if not question:
            return

        with st.spinner("Nour prépare votre réponse…"):
            try:
                answer = get_orchestrator().handle_question(
                    question=question,
                    advisor_id=advisor_id,
                    session_id=st.session_state.session_id,
                    profile=st.session_state.credit_profile,
                    conversation_history=st.session_state.chat_history,
                )
            except FileNotFoundError:
                st.error("La base documentaire n’est pas encore disponible.")
                return
            except Exception as exc:
                logging.exception("Assistant indisponible")
                st.error(f"L’assistant est momentanément indisponible : {exc}")
                return

        apply_assistant_result(answer)
        st.session_state.chat_history.append({
            "question": question,
            "answer": answer["answer"],
            "in_scope": answer.get("in_scope", False),
            "sources": answer.get("sources", []),
            "mode": answer.get("mode", "rag"),
            "profile_updates": answer.get("profile_updates", {}),
        })
        st.rerun()


# =========================================================
# FONCTIONS UTILITAIRES
# =========================================================


def validate_file(uploaded_file):
    """Valider le fichier uploadé"""
    if uploaded_file is None:
        return False, "Aucun fichier sélectionné"
    
    # Vérifier la taille
    if uploaded_file.size > settings.max_file_size_mb * 1024 * 1024:
        return False, f"Fichier trop volumineux (max {settings.max_file_size_mb} MB)"
    
    # Vérifier l'extension
    file_ext = Path(uploaded_file.name).suffix.lower()
    if file_ext not in settings.allowed_extensions:
        return False, f"Format non supporté. Formats acceptés : {', '.join(settings.allowed_extensions)}"
    
    # Vérifier le type MIME (optionnel)
    try:
        import magic
        mime = magic.from_buffer(uploaded_file.getvalue(), mime=True)
        allowed_mime = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']
        if mime not in allowed_mime:
            return False, f"Type MIME non supporté : {mime}"
    except Exception:
        # Si python-magic n'est pas disponible, on ignore cette vérification
        pass
    
    return True, "OK"


def count_pdf_pages(uploaded_file):
    """Compter les pages d'un PDF envoyé sans l'écrire sur le disque."""
    import fitz

    document = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
    try:
        return document.page_count
    finally:
        document.close()


def save_document_files(uploaded_files, document_type, doc_id):
    """Sauvegarder un document simple ou fusionner le recto-verso d'une CNIE."""
    files = list(uploaded_files or [])
    if not files:
        raise ValueError("Aucun fichier à sauvegarder")

    if len(files) == 1:
        extension = Path(files[0].name).suffix.lower()
        saved_path = UPLOAD_DIR / f"{doc_id}{extension}"
        saved_path.write_bytes(files[0].getvalue())
        return saved_path

    if document_type != "carte_identite" or len(files) != 2:
        raise ValueError("Seule la carte d'identité accepte deux fichiers")

    # PyMuPDF permet de produire un PDF unique quelle que soit la combinaison
    # choisie par l'utilisateur : image+image, PDF+image ou PDF+PDF.
    import fitz

    saved_path = UPLOAD_DIR / f"{doc_id}.pdf"
    combined = fitz.open()
    try:
        for uploaded in files:
            extension = Path(uploaded.name).suffix.lower().lstrip(".")
            source = fitz.open(stream=uploaded.getvalue(), filetype=extension)
            try:
                if source.is_pdf:
                    combined.insert_pdf(source)
                else:
                    image_pdf = fitz.open("pdf", source.convert_to_pdf())
                    try:
                        combined.insert_pdf(image_pdf)
                    finally:
                        image_pdf.close()
            finally:
                source.close()

        if combined.page_count != 2:
            raise ValueError(
                "Le document recto-verso doit produire exactement deux pages "
                f"(pages détectées : {combined.page_count})"
            )
        combined.save(saved_path, garbage=4, deflate=True)
    finally:
        combined.close()
    return saved_path

def save_session_state():
    """Sauvegarder l'état de la session"""
    try:
        session_dir = Path("data/sessions")
        session_dir.mkdir(parents=True, exist_ok=True)
        
        session_file = session_dir / f"session_{st.session_state.session_id}.pkl"
        with open(session_file, "wb") as f:
            # Exclure les objets non sérialisables
            state_to_save = {
                k: v for k, v in st.session_state.items()
                if not k.startswith("_") and not callable(v)
            }
            pickle.dump(state_to_save, f)
        return True
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de la session : {e}")
        return False

def load_session_state(session_id):
    """Restaurer l'état de la session"""
    try:
        session_file = Path("data/sessions") / f"session_{session_id}.pkl"
        if session_file.exists():
            with open(session_file, "rb") as f:
                saved_state = pickle.load(f)
                for key, value in saved_state.items():
                    if key not in ["orchestrator", "_orchestrator"]:
                        st.session_state[key] = value
            return True
    except Exception as e:
        logging.error(f"Erreur lors de la restauration de la session : {e}")
    return False



def request_document_analysis():
    """Verrouiller avant le rendu ; un second clic ne crée aucune demande."""
    if not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.analysis_requested = True


def process_document_with_progress(file_path, document_type, declared_data, advisor_id, session_id):
    """Indicateur réel d'activité, sans pourcentage simulé."""
    with st.status("Analyse du document en cours", expanded=True) as status:
        st.write("Lecture OCR, extraction et vérifications. Le délai dépend du nombre de pages.")
        st.caption("Patientez sans relancer l'analyse ; les résultats apparaîtront à la fin.")
        try:
            result = get_orchestrator().handle_document(
                pdf_path=str(file_path), document_type=document_type,
                advisor_id=advisor_id, session_id=session_id, declared_data=declared_data,
            )
        except Exception:
            status.update(label="L'analyse n'a pas abouti", state="error")
            raise
        status.update(label="Analyse terminée — résultats prêts à vérifier", state="complete", expanded=False)
        return result


def get_document_summary(doc_data):
    """Obtenir un résumé du document pour l'affichage"""
    filename = doc_data.get('filename', 'Document')
    doc_type = doc_data.get('type', 'Inconnu')
    status = doc_data.get('status', 'inconnu')
    
    status_icon = {
        'completed': '✅',
        'processing': '⏳',
        'error': '❌',
        'inconnu': '⏸️'
    }.get(status, '⏸️')
    
    return f"{status_icon} {filename} ({doc_type})"

# =========================================================
# INITIALISATION
# =========================================================

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# SESSION STATE - INITIALISATION AMÉLIORÉE
# =========================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "documents" not in st.session_state:
    st.session_state.documents = {}  # Structure: {doc_id: {"type": ..., "data": ...}}

if "current_doc_id" not in st.session_state:
    st.session_state.current_doc_id = None

if "current_client_id" not in st.session_state or not st.session_state.current_client_id:
    # Identifiant technique interne : le client n'a rien à saisir pour démarrer.
    st.session_state.current_client_id = f"client-{st.session_state.session_id[:8]}"

if "confirmed_fields" not in st.session_state:
    st.session_state.confirmed_fields = {}

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "credit_profile" not in st.session_state:
    st.session_state.credit_profile = {}

if "page" not in st.session_state:
    st.session_state.page = "Accueil"

if "theme" not in st.session_state:
    st.session_state.theme = "light"

if "processing" not in st.session_state:
    st.session_state.processing = False

if "last_error" not in st.session_state:
    st.session_state.last_error = None

if "assistant_open" not in st.session_state:
    st.session_state.assistant_open = False

if "account_created" not in st.session_state:
    st.session_state.account_created = False

if "customer_profile" not in st.session_state:
    st.session_state.customer_profile = {}

if "compromis_skipped" not in st.session_state:
    st.session_state.compromis_skipped = False
if "advisor_authenticated" not in st.session_state:
    st.session_state.advisor_authenticated = False

if "advisor_username" not in st.session_state:
    st.session_state.advisor_username = None

# L'ancienne page de chat est remplacée par l'assistant permanent à droite.
if st.session_state.page == "Assistant":
    st.session_state.page = "Accueil"

# =========================================================
# SIDEBAR AMÉLIORÉE AVEC GESTION CLIENT
# =========================================================

inject_app_styles()

advisor_id = (
    f"client_portal_"
    f"{st.session_state.session_id[:8]}"
)

if st.session_state.page != "Conseiller":
    render_assistant_dock(advisor_id)

# =========================================================
# APPLICATION DU THÈME
# =========================================================



# =========================================================
# RENDU DE L'EN-TÊTE
# =========================================================

if st.session_state.page != "Conseiller":
    render_header()

# =========================================================
# PAGE ACCUEIL
# =========================================================

if st.session_state.page == "Conseiller":
    if st.button(
        "Retour à l'espace client",
        icon=":material/arrow_back:",
        key="advisor_back_to_client",
    ):
        st.session_state.page = "Accueil"
        st.rerun()
    render_advisor_sidebar()
    render_advisor_dashboard()

elif st.session_state.page == "Accueil":
    if not st.session_state.account_created:
        render_cam_hero(
            "Crédit habitat · Espace client",
            "Commençons votre projet habitat",
            "Créez votre espace personnel pour sauvegarder vos justificatifs, "
            "reprendre votre parcours à tout moment et affiner votre simulation "
            "en toute autonomie.",
            "Données protégées · Validation par vos soins",
        )
        render_home_assurance_strip()
        st.stop()

    client_docs = current_client_documents()
    completed_types = completed_document_types(client_docs)
    required_types = {"carte_identite", "bulletin", "releve"}
    completed_required = len(required_types & completed_types)
    reviewed_types = reviewed_document_types(client_docs)
    documents_ready = required_types.issubset(reviewed_types)
    _, summary_rows, dossier_complete, missing_items = dossier_readiness()
    saved_project = (
        load_project(st.session_state.current_client_id)
        or st.session_state.get("quick_project", {})
    )

    if dossier_complete:
        hero_title = "Votre dossier est prêt pour la simulation."
        hero_text = (
            "Vos justificatifs et vos informations essentielles sont vérifiés. "
            "Vous pouvez maintenant comparer plusieurs scénarios de financement."
        )
        hero_badge = "DOSSIER COMPLET · INFORMATIONS VÉRIFIÉES"
    elif completed_required:
        hero_title = "Reprenez votre projet là où vous l’avez laissé."
        hero_text = (
            "Votre dossier est sauvegardé. Finalisez les justificatifs et vérifiez "
            "les informations détectées avant de lancer la simulation."
        )
        hero_badge = f"{completed_required}/3 JUSTIFICATIFS TRAITÉS"
    else:
        hero_title = "Construisez votre projet immobilier en toute simplicité."
        hero_text = (
            "Déposez vos justificatifs, contrôlez les informations détectées et "
            "obtenez une estimation personnalisée de votre financement."
        )
        hero_badge = "PARCOURS SÉCURISÉ · VALIDATION PAR LE CLIENT"

    render_cam_hero(
        "Crédit habitat · Espace personnel",
        hero_title,
        hero_text,
        hero_badge,
    )
    render_home_assurance_strip()

    # -----------------------------------------------------
    # SYNTHÈSE OU FORMULAIRE DU PROJET
    # -----------------------------------------------------

    editing_project = st.session_state.get("editing_home_project", False)

    if saved_project and not editing_project:
        with st.container(key="home_project_summary", border=True):
            summary_title, summary_action = st.columns(
                [4, 1], vertical_alignment="center"
            )
            with summary_title:
                st.markdown("### Votre projet immobilier")
                st.markdown(
                    '<div class="home-status-line"><span class="home-status-dot"></span>'
                    '<span>Projet enregistré</span></div>',
                    unsafe_allow_html=True,
                )
            with summary_action:
                if st.button(
                    "Modifier", icon=":material/edit:", width="stretch",
                    key="edit_home_project",
                ):
                    st.session_state.editing_home_project = True
                    st.rerun()

            project_metrics = st.columns(4)
            project_metrics[0].metric(
                "Ville", saved_project.get("city") or "À préciser", border=True
            )
            project_metrics[1].metric(
                "Type de bien", saved_project.get("property_type") or "À préciser", border=True
            )
            project_metrics[2].metric(
                "Budget",
                f"{float(saved_project.get('purchase_price') or 0):,.0f} MAD",
                border=True,
            )
            project_metrics[3].metric(
                "Durée",
                f"{int(saved_project.get('duration_years') or 20)} ans",
                border=True,
            )

    if not saved_project or editing_project:
        with st.container(key="home_project_summary", border=True):
            st.markdown("### Personnaliser mon projet")
            st.caption("Ces informations seront reprises automatiquement dans vos simulations.")
            with st.form("housing_project_profile"):
                project_left, project_right = st.columns(2)
                city = project_left.text_input(
                    "Ville du projet", value=saved_project.get("city") or ""
                )
                property_options = ["Appartement", "Maison", "Terrain + construction", "Autre"]
                saved_type = saved_project.get("property_type") or property_options[0]
                property_type = project_right.selectbox(
                    "Type de bien", property_options,
                    index=property_options.index(saved_type) if saved_type in property_options else 0,
                )
                purchase_price = project_left.number_input(
                    "Budget estimé (MAD)", min_value=0.0,
                    value=float(saved_project.get("purchase_price") or 600000), step=10000.0,
                )
                contribution = project_right.number_input(
                    "Apport personnel (MAD)", min_value=0.0,
                    value=float(saved_project.get("contribution") or 100000), step=5000.0,
                )
                duration_years = st.slider(
                    "Durée souhaitée", 5, 30,
                    int(saved_project.get("duration_years") or 20), format="%d ans",
                )
                save_project_button = st.form_submit_button(
                    "Enregistrer mon projet", type="primary", width="stretch"
                )
            if save_project_button:
                if contribution > purchase_price:
                    st.error("L'apport ne peut pas dépasser le prix estimé du bien.")
                else:
                    save_project(
                        st.session_state.current_client_id, city.strip(), property_type,
                        purchase_price, contribution, duration_years,
                    )
                    st.session_state.editing_home_project = False
                    st.toast("Votre projet est enregistré.", icon=":material/check_circle:")
                    st.rerun()

    # -----------------------------------------------------
    # ACTIONS CONTEXTUELLES
    # -----------------------------------------------------

    if dossier_complete:
        primary_title = "Votre simulation est disponible"
        primary_text = "Consultez votre mensualité, votre capacité d’emprunt et comparez les durées."
        primary_caption = "Données issues de vos informations vérifiées"
        primary_label = "Voir ma simulation"
        primary_icon = ":material/analytics:"
        primary_page = "Simulation"
    elif documents_ready:
        primary_title = "Vérifier mes informations"
        primary_text = "Contrôlez les informations essentielles extraites de vos justificatifs."
        primary_caption = "Dernière étape avant votre simulation"
        primary_label = "Continuer la vérification"
        primary_icon = ":material/fact_check:"
        primary_page = "Verification"
    else:
        primary_title = "Continuer mon dossier"
        primary_text = "Ajoutez vos justificatifs pour obtenir une simulation personnalisée."
        primary_caption = f"{completed_required}/3 justificatifs obligatoires traités"
        primary_label = "Accéder à mes justificatifs"
        primary_icon = ":material/upload_file:"
        primary_page = "Extraction"

    action_left, action_right = st.columns(2, gap="large")
    with action_left:
        with st.container(key="home_primary_action", border=True, height="stretch"):
            st.markdown(f"### {primary_title}")
            st.write(primary_text)
            st.caption(primary_caption)
            if st.button(
                primary_label, icon=primary_icon, type="primary", width="stretch",
                disabled=st.session_state.processing, key="home_primary_action_button",
            ):
                st.session_state.page = primary_page
                st.rerun()

    with action_right:
        with st.container(key="home_secondary_action", border=True, height="stretch"):
            st.markdown("### Explorer une autre hypothèse")
            st.write(
                "Estimez une mensualité, calculez votre capacité d’emprunt "
                "ou comparez plusieurs durées."
            )
            st.caption("Calcul immédiat · Modifiable · Non contractuel")
            if st.button(
                "Ouvrir les outils de simulation", icon=":material/calculate:",
                width="stretch", disabled=st.session_state.processing, key="home_quick",
            ):
                st.session_state.page = "Estimation"
                st.rerun()

    # -----------------------------------------------------
    # ÉTAT DU DOSSIER
    # -----------------------------------------------------

    st.markdown('<div class="ca-section-title">État de votre dossier</div>', unsafe_allow_html=True)
    st.caption("Une vue synthétique des éléments nécessaires à votre simulation personnalisée.")
    status_columns = st.columns(3, gap="medium")

    with status_columns[0]:
        with st.container(border=True, height="stretch"):
            st.caption("PROJET IMMOBILIER")
            st.markdown("### " + ("Renseigné" if saved_project else "À compléter"))
            st.write(
                "Votre budget, votre apport et la durée sont enregistrés."
                if saved_project else
                "Renseignez les caractéristiques principales de votre projet."
            )

    with status_columns[1]:
        with st.container(border=True, height="stretch"):
            st.caption("JUSTIFICATIFS")
            st.markdown(f"### {completed_required} sur 3")
            st.write(
                "Les trois justificatifs obligatoires ont été analysés."
                if completed_required == 3 else
                f"Il reste {3 - completed_required} justificatif(s) obligatoire(s) à traiter."
            )

    with status_columns[2]:
        with st.container(border=True, height="stretch"):
            st.caption("VÉRIFICATION")
            st.markdown("### " + ("Terminée" if dossier_complete else "En attente"))
            st.write(
                "Les informations indispensables sont confirmées."
                if dossier_complete else
                "La simulation personnalisée sera disponible après vérification."
            )

    with st.container(key="home_help_banner", border=True):
        help_text, help_action = st.columns([3.4, 1], vertical_alignment="center")
        with help_text:
            st.markdown("### Une question sur votre crédit habitat ?")
            st.caption(
                "Nour vous explique les documents, les étapes et les conditions "
                "à partir de la documentation disponible."
            )
        with help_action:
            if st.button(
                "Poser une question", icon=":material/chat:",
                width="stretch", key="home_ask_question",
            ):
                st.session_state.assistant_open = True
                st.rerun()

    with st.container(border=True):
        st.markdown("**Une estimation pour mieux vous orienter**")
        st.caption(
            "Le résultat fourni est indicatif et ne constitue ni un accord de crédit ni une offre contractuelle. "
            "La banque étudiera votre dossier complet avant toute décision."
        )


# =========================================================
# PAGE EXTRACTION AMÉLIORÉE AVEC GESTION MULTI-DOCUMENTS
# =========================================================

elif st.session_state.page == "Extraction":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    st.title("Mon parcours de crédit habitat")
    st.caption(
        "Avancez simplement, une étape après l'autre. Le prochain document à "
        "ajouter est sélectionné automatiquement."
    )
    reset_notice = st.session_state.pop("documents_reset_notice", None)
    if reset_notice:
        st.success(reset_notice, icon=":material/check_circle:")
    journey_notice = st.session_state.pop("journey_notice", None)
    if journey_notice:
        st.success(journey_notice, icon=":material/check_circle:")
    
    # -----------------------------------------------------
    # LISTE DES DOCUMENTS DU CLIENT
    # -----------------------------------------------------
    
    client_docs = {
        doc_id: doc_data 
        for doc_id, doc_data in st.session_state.documents.items()
        if doc_data.get("client_id") == st.session_state.current_client_id
    }

    journey_step = credit_journey_step(client_docs)
    _, _, dossier_complete, _ = dossier_readiness()

    # Si le document de l'étape a déjà été analysé, le sélectionner afin que
    # l'utilisateur puisse relire et corriger ses champs avant de continuer.
    if journey_step < len(DOCUMENT_JOURNEY):
        active_document_type = DOCUMENT_JOURNEY[journey_step]["type"]
        selected_document = st.session_state.documents.get(
            st.session_state.current_doc_id
        )
        if not selected_document:
            matching_documents = [
                (document_id, document)
                for document_id, document in client_docs.items()
                if document.get("type") == active_document_type
                and document.get("status") == "completed"
            ]
            matching_documents.sort(
                key=lambda item: item[1].get("timestamp") or "",
                reverse=True,
            )
            if matching_documents:
                selected_id, selected_document = matching_documents[0]
                st.session_state.current_doc_id = selected_id
                st.session_state.last_result = selected_document.get("result")
                st.session_state.confirmed_fields = selected_document.get(
                    "confirmed_fields", {}
                )

    # Un dossier finalisé reste entièrement consultable depuis « Mes documents ».
    # L'étape 6 sert uniquement à afficher toutes les coches dans ce cas.
    render_credit_journey(6 if dossier_complete else journey_step)
    st.divider()
    
    with st.expander("Voir et modifier mes documents", expanded=dossier_complete):
        if client_docs:

            # Afficher les documents dans une grille
            cols = st.columns(2)
            for idx, (doc_id, doc_data) in enumerate(client_docs.items()):
                col = cols[idx % 2]
                with col:
                    is_active = doc_id == st.session_state.current_doc_id
                    status = doc_data.get('status', 'inconnu')

                    # Couleur selon le statut
                    status_color = {
                        'completed': '✅',
                        'processing': '⏳',
                        'error': '❌',
                        'inconnu': '⏸️'
                    }.get(status, '⏸️')

                    status_text = {
                        'completed': 'Traité',
                        'processing': 'En cours...',
                        'error': 'Erreur',
                        'inconnu': 'En attente'
                    }.get(status, 'En attente')

                    with st.container(border=True):
                        col_btn, col_status = st.columns([3, 1])
                        with col_btn:
                            if st.button(
                                f"📄 {doc_data.get('filename', 'Document')[:30]}...",
                                key=f"view_{doc_id}",
                                width="stretch",
                            ):
                                st.session_state.current_doc_id = doc_id
                                st.session_state.last_result = doc_data.get('result')
                                st.session_state.confirmed_fields = doc_data.get('confirmed_fields', {})
                                st.rerun()
                        with col_status:
                            st.caption(f"{status_color} {status_text}")

                        # Infos supplémentaires
                        st.caption(f"Type: {doc_data.get('type', 'Inconnu')}")
                        if doc_data.get('timestamp'):
                            st.caption(f"📅 {doc_data.get('timestamp')[:16]}")
                        if st.button(
                            "Supprimer ce justificatif",
                            icon=":material/delete:",
                            key=f"delete_card_{doc_id}",
                            width="stretch",
                        ):
                            delete_one_document_dialog(doc_id)

                    st.write("")  # Espacement

            if st.button(
                "Recommencer avec de nouveaux justificatifs",
                icon=":material/delete_sweep:",
                key="reset_all_documents",
            ):
                reset_documents_dialog()

            st.divider()

    selected = st.session_state.documents.get(st.session_state.current_doc_id)
    if selected and selected.get("status") == "completed" and selected.get("result"):
        render_guided_document_review(st.session_state.current_doc_id, selected, journey_step, advisor_id)
        st.stop()

    if journey_step >= 4:
        st.success(
            "Vos justificatifs sont enregistrés. Cliquez sur un document ci-dessus "
            "pour revoir ou corriger ses informations."
        )
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button(
                "Revoir mes informations",
                icon=":material/fact_check:",
                width="stretch",
                key="documents_open_verification",
            ):
                st.session_state.page = "Verification"
                st.rerun()
      

        if st.session_state.get("compromis_skipped", False):
            if st.button(
                "Ajouter mon compromis de vente",
                icon=":material/upload_file:",
                width="stretch",
                key="documents_add_compromis",
            ):
                st.session_state.compromis_skipped = False
                st.session_state.current_doc_id = None
                st.session_state.last_result = None
                st.rerun()
        st.stop()

    document_step = DOCUMENT_JOURNEY[journey_step]
    document_type = document_step["type"]

    st.subheader(f"Étape {journey_step + 1} — {document_step['title']}")
    st.write(document_step["instruction"])

    if document_step["optional"]:
        st.info(
            "Cette étape est facultative. Vous pouvez continuer même si vous "
            "n'avez pas encore signé de compromis."
        )
        if st.button(
            "Continuer sans compromis",
            icon=":material/skip_next:",
            width="stretch",
            key="skip_optional_compromis",
        ):
            st.session_state.compromis_skipped = True
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.rerun()
    
    # -----------------------------------------------------
    # AJOUTER UN NOUVEAU DOCUMENT
    # -----------------------------------------------------
    
    declared_data = {}
    with st.container():
        is_identity = document_type == "carte_identite"
        identity_mode = None

        if is_identity:
            identity_mode = st.radio(
                "Format de la carte d'identité",
                options=("PDF unique recto-verso", "Deux fichiers séparés"),
                horizontal=True,
                disabled=st.session_state.processing,
                key=f"identity_mode_{st.session_state.current_client_id}",
            )

            if identity_mode == "PDF unique recto-verso":
                identity_pdf = st.file_uploader(
                    "PDF contenant le recto et le verso",
                    type=["pdf"],
                    accept_multiple_files=False,
                    help="Le PDF doit contenir exactement deux pages, dans l'ordre recto puis verso.",
                    key=f"identity_pdf_{st.session_state.current_client_id}",
                )
                uploaded_files = [identity_pdf] if identity_pdf is not None else []
            else:
                recto = st.file_uploader(
                    "Recto de la carte",
                    type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                    accept_multiple_files=False,
                    key=f"identity_recto_{st.session_state.current_client_id}",
                )
                verso = st.file_uploader(
                    "Verso de la carte",
                    type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                    accept_multiple_files=False,
                    key=f"identity_verso_{st.session_state.current_client_id}",
                )
                uploaded_files = [file for file in (recto, verso) if file is not None]
        else:
            uploaded_value = st.file_uploader(
                "Déposer un document",
                type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                accept_multiple_files=False,
                help=(
                    f"Formats acceptés : {', '.join(settings.allowed_extensions)}. "
                    f"Taille max : {settings.max_file_size_mb} MB"
                ),
                key=f"uploader_{st.session_state.current_client_id}_{document_type}",
            )
            uploaded_files = [uploaded_value] if uploaded_value is not None else []

        upload_ready = bool(uploaded_files)

        if is_identity and identity_mode == "Deux fichiers séparés" and len(uploaded_files) != 2:
            upload_ready = False
            st.caption("Ajoutez les deux faces pour activer l'analyse.")

        if uploaded_files:
            invalid_messages = []
            for selected_file in uploaded_files:
                is_valid, message = validate_file(selected_file)
                if not is_valid:
                    invalid_messages.append(f"{selected_file.name} : {message}")

            total_size = sum(selected_file.size for selected_file in uploaded_files)
            if total_size > settings.max_file_size_mb * 1024 * 1024:
                invalid_messages.append(
                    f"Taille totale trop importante (max {settings.max_file_size_mb} MB)"
                )

            if (
                is_identity
                and identity_mode == "PDF unique recto-verso"
                and not invalid_messages
            ):
                try:
                    page_count = count_pdf_pages(uploaded_files[0])
                    if page_count != 2:
                        invalid_messages.append(
                            f"Le PDF doit contenir exactement 2 pages ; il en contient {page_count}."
                        )
                except Exception:
                    invalid_messages.append("Le PDF est illisible ou endommagé.")

            if invalid_messages:
                upload_ready = False
                for message in invalid_messages:
                    st.error(f"⚠️ {message}")
            else:
                for index, selected_file in enumerate(uploaded_files):
                    if is_identity and identity_mode == "Deux fichiers séparés":
                        label = "Recto" if index == 0 else "Verso"
                    elif is_identity:
                        label = "PDF recto-verso"
                    else:
                        label = "Document"
                    st.success(f"✅ {label} : {selected_file.name}")
                st.caption(f"📦 Taille totale : {total_size / 1024:.1f} KB")
    
    # -----------------------------------------------------
    # ERREUR PERSISTEE (affichée après un st.rerun() suite à un échec)
    # -----------------------------------------------------

    if st.session_state.get("last_error"):
        st.error(f"❌ Erreur lors du traitement : {st.session_state.last_error}")
        with st.expander("🔍 Détails techniques"):
            st.code(st.session_state.last_error)
        if st.button("Fermer ce message"):
            st.session_state.last_error = None
            st.rerun()
        st.divider()

    # Boutons d'action
    with st.container():
        st.button(
            "Lire mon document",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            disabled=st.session_state.processing or not upload_ready,
            key="launch_document_analysis",
            on_click=request_document_analysis,
        )
    # -----------------------------------------------------
    # EXECUTION AMÉLIORÉE
    # -----------------------------------------------------
    
    if st.session_state.pop("analysis_requested", False):
        if not st.session_state.current_client_id:
            st.session_state.processing = False
            st.error("⚠️ Veuillez renseigner un identifiant client")
            st.stop()
        
        if not upload_ready:
            st.session_state.processing = False
            st.error("⚠️ Déposez un document avant de lancer l'analyse")
            st.stop()
        

        
        # Créer un ID unique pour ce document
        doc_id = str(uuid.uuid4())
        
        # Stocker le document dans la session
        st.session_state.documents[doc_id] = {
            "client_id": st.session_state.current_client_id,
            "type": document_type,
            "filename": (
                " + ".join(file.name for file in uploaded_files)
                if len(uploaded_files) > 1 else uploaded_files[0].name
            ),
            "timestamp": datetime.now().isoformat(),
            "status": "processing",
            "result": None,
            "confirmed_fields": {},
            "journey_reviewed": False,
            "declared_data": declared_data
        }
        
        st.session_state.current_doc_id = doc_id
        
        # Traiter avec progression
        st.session_state.processing = True
        st.session_state.last_error = None
        
        try:
            saved_path = save_document_files(uploaded_files, document_type, doc_id)
            st.session_state.documents[doc_id]["document_path"] = str(saved_path)
            result = process_document_with_progress(
                file_path=saved_path,
                document_type=document_type,
                declared_data=declared_data,
                advisor_id=advisor_id,
                session_id=st.session_state.session_id
            )
            
            # Mettre à jour les données du document
            st.session_state.documents[doc_id]["result"] = result
            st.session_state.documents[doc_id]["status"] = "completed"
            st.session_state.last_result = result
            st.session_state.confirmed_fields = {}
            save_document(
                st.session_state.current_client_id, doc_id,
                st.session_state.documents[doc_id],
            )
            st.session_state.journey_notice = (
                f"{document_step['title']} analysé avec succès. Vérifiez et "
                "corrigez maintenant les informations extraites avant de continuer."
            )
            if document_type == "compromis":
                st.session_state.compromis_skipped = False
            
            # Log dans l'audit
            try:
                audit.log_document_processed(
                    document_id=doc_id,
                    document_type=document_type,
                    client_id=st.session_state.current_client_id,
                    advisor_id=advisor_id,
                    status="completed"
                )
            except Exception:
                pass
            
        except Exception as e:
            st.session_state.documents[doc_id]["status"] = "error"
            # st.error() affiché juste avant st.rerun() disparaît
            # instantanément (le rerun efface tout ce qui vient d'être
            # rendu) : on stocke le message en session_state pour le
            # ré-afficher après le rerun, au lieu de le perdre.
            st.session_state.last_error = str(e)
            logging.exception(
                "[Interface] Échec du traitement du document %s", doc_id
            )
        finally:
            st.session_state.processing = False
            st.rerun()
    
    # -----------------------------------------------------
# PAGE VÉRIFICATION DES INFORMATIONS ESSENTIELLES
# =========================================================

elif st.session_state.page == "Verification":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    client_docs = current_client_documents()
    if not required_documents_ready(client_docs):
        st.title("Vérification indisponible")
        st.warning(
            "Ajoutez d'abord votre carte d'identité, votre bulletin de paie "
            "et votre relevé bancaire."
        )
        if st.button(
            "Retourner à mes documents",
            icon=":material/upload_file:",
            type="primary",
            width="stretch",
        ):
            st.session_state.page = "Extraction"
            st.rerun()
        st.stop()

    st.title("Vérifier mes informations")
    st.caption(
        "Retrouvez vos informations déjà corrigées. Vous pouvez les modifier avant votre "
        "simulation."
    )
    render_final_verification(
        client_docs,
        st.session_state.current_client_id,
        advisor_id,
        st.session_state.session_id,
    )
    if st.button("Retourner à mes documents", icon=":material/arrow_back:"):
        st.session_state.page = "Extraction"
        st.rerun()

# =========================================================
# PAGE SIMULATION CLIENT
# =========================================================

elif st.session_state.page == "Estimation":
    st.title("Préparer mon projet habitat")

    st.caption(
        "Estimez votre mensualité ou découvrez votre "
        "capacité d'emprunt, sans compte ni justificatif."
    )

    simulation_tab, capacity_tab = st.tabs([
        "Estimer ma mensualité",
        "Calculer ma capacité d'emprunt",
    ])

    estimate = None
    quick_profile = st.session_state.get("credit_profile", {})
    quick_income = float(
        quick_profile.get("revenu_mensuel_net") or 0
    ) + float(
        quick_profile.get("autres_revenus_mensuels") or 0
    )
    quick_charges = float(
        quick_profile.get("charges_mensuelles") or 0
    )
    quick_project = st.session_state.get("quick_project", {})

    with simulation_tab:
        estimate = render_simulation(
            project=quick_project,
            key_prefix="quick",
            income=quick_income or None,
            existing_monthly_charges=quick_charges,
        )

    with capacity_tab:
        render_borrowing_capacity(
            project=quick_project,
            key_prefix="quick_capacity",
            income=quick_income or None,
            existing_monthly_charges=quick_charges,
        )

    if st.button(
        "Affiner avec mes documents",
        type="primary",
        key="quick_refine",
        width="stretch",
    ):
        if estimate:
            st.session_state.quick_project = estimate

        st.session_state.page = (
            "Extraction"
            if st.session_state.account_created
            else "Accueil"
        )

        st.rerun()

elif st.session_state.page == "Simulation":
    if not st.session_state.account_created:
        st.session_state.page = "Estimation"
        st.rerun()

    client_docs, _, dossier_complete, _ = dossier_readiness()

    if not dossier_complete:
        st.session_state.page = "Verification"
        st.rerun()

    st.title("Ma simulation de crédit habitat")

    st.caption(
        "Simulez votre crédit et comparez plusieurs durées "
        "avant de choisir le scénario adapté à votre projet."
    )

    saved_project = (
        load_project(st.session_state.current_client_id)
        or st.session_state.get("quick_project", {})
    )

    rows, _ = build_client_summary(client_docs)

    confirmed = {
        row["field"]: row["Valeur confirmée"]
        for row in rows
        if row["Statut"] == "Confirmé"
    }

    def confirmed_number(field_name):
        try:
            return float(
                confirmed.get(field_name) or 0
            )
        except (TypeError, ValueError):
            return 0.0

    income = (
        confirmed_number("salaire_net")
        + confirmed_number("revenus_complementaires")
    )

    existing_charges = confirmed_number(
        "charge_mensuelle_credits"
    )

    simulation_tab, capacity_tab = st.tabs([
    "Simuler ma mensualité",
    "Ma capacité d'emprunt",
])

    estimate = None
    capacity = None

    with simulation_tab:
         estimate = render_simulation(
        project=saved_project,
        key_prefix=(
            f"simulation_"
            f"{st.session_state.current_client_id}"
        ),
        income=income,
        existing_monthly_charges=existing_charges,
    )

    with capacity_tab:
         capacity = render_borrowing_capacity(
        project=saved_project,
        key_prefix=(
            f"capacity_"
            f"{st.session_state.current_client_id}"
        ),
        income=income,
        existing_monthly_charges=existing_charges,
    )
    with st.expander(
        "Ma situation vérifiée"
    ):
        for row in rows:
            st.write(
                f"{row['Champ']} : "
                f"{row['Valeur confirmée']}"
            )

    if st.button(
        "Modifier ma situation",
        key="simulation_edit",
        icon=":material/edit:",
    ):
        st.session_state.page = "Verification"
        st.rerun()

# =========================================================
# PAGE ASSISTANT AMÉLIORÉE
# =========================================================

elif st.session_state.page == "Assistant":
    st.title("Comprendre mon crédit habitat")
    
    st.caption(
        "Posez une question sur les offres, les conditions et la préparation de votre projet."
    )
    
    # Actions rapides
    col_new, _ = st.columns([1, 3])
    with col_new:
        if st.button("🆕 Nouvelle conversation", width="stretch"):
            st.session_state.chat_history = []
            st.session_state.credit_profile = {}
            st.rerun()
    
    st.divider()
    
    # -----------------------------------------------------
    # QUESTIONS RAPIDES
    # -----------------------------------------------------
    
    st.caption("⚡ Questions rapides")
    
    quick_1, quick_2, quick_3 = st.columns(3)
    quick_question = None
    
    with quick_1:
        if st.button(
            "📋 Conditions d'éligibilité",
            width="stretch",
            help="Quelles sont les conditions d'éligibilité au crédit habitat ?"
        ):
            quick_question = "Quelles sont les conditions d'éligibilité au crédit habitat ?"
    
    with quick_2:
        if st.button(
            "📎 Documents nécessaires",
            width="stretch",
            help="Quels documents sont nécessaires pour constituer un dossier de crédit habitat ?"
        ):
            quick_question = "Quels documents sont nécessaires pour constituer un dossier de crédit habitat ?"
    
    with quick_3:
        if st.button(
            "💰 Taux du crédit",
            width="stretch",
            help="Quel est le taux d'intérêt du crédit habitat ?"
        ):
            quick_question = "Quel est le taux d'intérêt du crédit habitat ?"
    
    st.write("")
    
    # -----------------------------------------------------
    # HISTORIQUE
    # -----------------------------------------------------
    
    for exchange in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(exchange["question"])
        
        with st.chat_message("assistant"):
            if exchange.get("mode") == "guidance":
                st.badge(
                    "Accompagnement personnalisé",
                    color="green",
                    icon=":material/account_circle:",
                )
                st.write(exchange["answer"])
            elif exchange.get("in_scope", False):
                st.badge("Réponse documentée", color="green", icon=":material/library_books:")
                st.write(exchange["answer"])
                
                if exchange.get("sources"):
                    with st.expander("📖 Sources utilisées"):
                        for source in exchange["sources"]:
                            st.write(f"• {source}")
            else:
                st.badge("Question hors périmètre", color="orange")
                st.warning(exchange["answer"])
    
    # -----------------------------------------------------
    # QUESTION
    # -----------------------------------------------------
    
    question = st.chat_input("💬 Posez votre question...")
    
    if quick_question:
        question = quick_question
    
    # -----------------------------------------------------
    # EXECUTION
    # -----------------------------------------------------
    
    if question:
        with st.chat_message("user"):
            st.write(question)
        
        with st.chat_message("assistant"):
            with st.spinner("🔍 Recherche dans la documentation..."):
                try:
                    chat_result = get_orchestrator().handle_question(
                        question=question,
                        advisor_id=advisor_id,
                        session_id=st.session_state.session_id,
                        profile=st.session_state.credit_profile,
                        conversation_history=st.session_state.chat_history,
                    )
                except FileNotFoundError:
                    st.error(
                        "❌ Le vectorstore RAG n'existe pas encore. "
                        "Lancez `python -m rag.ingest` après avoir ajouté les documents dans `data/docs/`."
                    )
                    st.stop()
                except Exception as e:
                    st.error(f"❌ Erreur lors du traitement : {str(e)}")
                    st.stop()
            
            if chat_result.get("mode") == "guidance":
                st.badge(
                    "Accompagnement personnalisé",
                    color="green",
                    icon=":material/account_circle:",
                )
                st.write(chat_result["answer"])
            elif chat_result.get("in_scope", False):
                st.badge("Réponse documentée", color="green", icon=":material/library_books:")
                st.write(chat_result["answer"])
                
                if chat_result.get("sources"):
                    with st.expander("📖 Sources utilisées"):
                        for source in chat_result["sources"]:
                            st.write(f"• {source}")
            else:
                st.badge("Question hors périmètre", color="orange")
                st.warning(chat_result["answer"])
        
        # Ajouter à l'historique
        apply_assistant_result(chat_result)
        st.session_state.chat_history.append({
            "question": question,
            "answer": chat_result["answer"],
            "in_scope": chat_result.get("in_scope", False),
            "sources": chat_result.get("sources", []),
            "mode": chat_result.get("mode", "rag"),
            "profile_updates": chat_result.get("profile_updates", {}),
        })
        
        st.rerun()

# L'assistant est rendu après le contenu mais reste fixé à droite par CSS.

# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption("Crédit Agricole du Maroc — Assistant Crédit Habitat")

# =========================================================
# GESTION DES ERREURS GLOBALES
# =========================================================

if "error" in st.session_state:
    st.error(f"⚠️ {st.session_state.error}")
    if st.button("Effacer l'erreur", key="clear_global_error"):
        del st.session_state.error
        st.rerun()
