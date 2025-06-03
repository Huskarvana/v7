import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import random
import transformers
import torch
from transformers import pipeline

# --- CONFIGURATION ---
st.set_page_config(page_title="Veille DS Automobiles", layout="wide")
st.title("🚗 Agent de Veille – DS Automobiles (APIs multiples)")

API_KEY_NEWSDATA = st.secrets["API_KEY_NEWSDATA"]
NEWSDATA_URL = "https://newsdata.io/api/1/news"
MEDIASTACK_API_KEY = st.secrets["MEDIASTACK_API_KEY"]
MEDIASTACK_URL = "http://api.mediastack.com/v1/news"
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=DS+Automobiles&hl=fr&gl=FR&ceid=FR:fr",
    "https://www.leblogauto.com/feed"
]
SLACK_WEBHOOK_URL = st.secrets["SLACK_WEBHOOK_URL"]  # À remplacer par ton vrai webhook

MODELES_DS = ["DS N4", "DS N8", "DS7", "DS3", "DS9", "DS4", "Jules Verne"]

@st.cache_resource
def get_sentiment_pipeline():
    return pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment")
sentiment_analyzer = get_sentiment_pipeline()

def fetch_newsdata_articles(query, max_results=5):
    params = {"apikey": API_KEY_NEWSDATA, "q": query, }
    try:
        response = requests.get(NEWSDATA_URL, params=params)
        data = response.json()
        return [{
            "date": item.get("pubDate", ""),
            "titre": item.get("title", ""),
            "contenu": item.get("description", ""),
            "source": item.get("source_id", ""),
            "lien": item.get("link", "")
        } for item in data.get("results", [])[:max_results]]
    except:
        return []

def fetch_mediastack_articles(query, max_results=5):
    params = {"access_key": MEDIASTACK_API_KEY, "keywords": query, }
    try:
        response = requests.get(MEDIASTACK_URL, params=params)
        data = response.json()
        return [{
            "date": item.get("published_at", ""),
            "titre": item.get("title", ""),
            "contenu": item.get("description", ""),
            "source": item.get("source", ""),
            "lien": item.get("url", "")
        } for item in data.get("data", [])[:max_results]]
    except:
        return []

def detecter_modele(titre):
    for m in MODELES_DS:
        if m.lower() in titre.lower():
            return m
    return "DS Global"

def analyser_article(row):
    contenu = row.get("contenu") or ""
    try:
        sentiment = sentiment_analyzer(contenu[:512])[0]["label"]
    except:
        sentiment = "neutral"
    modele = detecter_modele(row.get("titre") or "")
    résumé = contenu[:200] + "..." if contenu else "Aucun contenu"
    return pd.Series({"résumé": résumé, "ton": sentiment.capitalize(), "modèle": modele})

def envoyer_notif_slack(article):
    try:
        payload = {
            "text": f"📰 Nouvel article détecté sur *{article['modèle']}*\n" f"*{article['titre']}*\n" f"_Ton: {article['ton']}_\n" f"<{article['lien']}|Lire l\'article>"
        }
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    except:
        pass

# Interface utilisateur
nb_articles = st.slider("Nombre d'articles à récupérer (par source)", 5, 30, 10)
filtre_modele = st.selectbox("Filtrer par modèle", ["Tous"] + MODELES_DS)
filtre_ton = st.selectbox("Filtrer par ton", ["Tous", "Positive", "Neutral", "Negative"])

if st.button("🔍 Lancer la veille"):
    newsdata = fetch_newsdata_articles("DS Automobiles", nb_articles)
    mediastack = fetch_mediastack_articles("DS Automobiles", nb_articles)
    articles = pd.DataFrame(newsdata + mediastack)

    if not articles.empty:
        with st.spinner("Analyse en cours..."):
            articles[['résumé', 'ton', 'modèle']] = articles.apply(analyser_article, axis=1)

        articles['date'] = pd.to_datetime(articles['date'], errors='coerce')
        articles = articles.sort_values(by='date', ascending=False)

        for _, row in articles.iterrows():
            envoyer_notif_slack(row)

        if filtre_modele != "Tous":
            articles = articles[articles['modèle'] == filtre_modele]
        if filtre_ton != "Tous":
            articles = articles[articles['ton'] == filtre_ton]

        mentions_today = len(articles)
        moyenne_7j = 25 / 7
        indice = int((mentions_today / max(moyenne_7j, 1)) * 50 + random.randint(0, 20))
        niveau = '🔴 Pic' if indice > 75 else '🟡 Stable' if indice > 50 else '🟢 Faible'

        st.metric("Indice de notoriété", f"{indice}/100", niveau)
        st.dataframe(articles[['date', 'titre', 'modèle', 'ton', 'résumé', 'source', 'lien']])
    else:
        st.warning("Aucun article trouvé.")
