import asyncio
import json
import os
import streamlit as st
import pandas as pd
import warnings
from datetime import datetime, timedelta
from deriv_api import DerivAPI

# Masquer les avertissements de la console
warnings.filterwarnings("ignore")

# Configuration de la page Web Streamlit
st.set_page_config(page_title="Bot Boom 1000", page_icon="📈", layout="wide")

# =====================================================================
# 1. PARAMÈTRES ET CONSTANTES FIXES
# =====================================================================
APP_ID = '119914'
TOKEN = 'xBPOeSK61N5Hm42'
MIN_STAKE_DERIV = 1.0

# Initialisation des fichiers de stockage temporaire pour l'interface
STATUS_FILE = "bot_status.json"

def initialiser_fichiers():
    if not os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "w") as f:
            json.dump({
                "balance": 0.0, "active_trade": "Aucun", 
                "logs": "🤖 Système initialisé. En attente de connexion...",
                "morphology": "N/A"
            }, f)

initialiser_fichiers()

# =====================================================================
# 2. FONCTIONS DE TRADING ASYNCHRONES (MOTEUR DERIV)
# =====================================================================
async def recuperer_capital_reel(api):
    try:
        balance_data = await api.balance()
        if 'balance' in balance_data:
            return float(balance_data['balance']['balance'])
    except:
        pass
    return None

def analyser_anatomie_spike(df):
    if df is None or len(df) < 15:
        return False, False
    last_finished = df.iloc[-2]
    corps = last_finished['close'] - last_finished['open']
    meche_sup = last_finished['high'] - last_finished['close']
    
    seuil_dynamique = df[df['close'] - df['open'] > 0]['close'] - df[df['close'] - df['open'] > 0]['open']
    seuil_spike = seuil_dynamique.mean() * 2.5
    
    is_spike = corps > seuil_spike
    is_exhaustion_spike = is_spike and (meche_sup <= 0.1)
    return is_spike, is_exhaustion_spike

async def executer_contrat_multdown(api, symbol, stake, multiplier):
    try:
        buy = await api.buy({
            "buy": 1, "price": float(stake),
            "parameters": {
                "amount": float(stake), "basis": "stake",
                "contract_type": "MULTDOWN", "multiplier": int(multiplier),
                "currency": "USD", "symbol": symbol
            }
        })
        if 'buy' in buy:
            return buy['buy']['contract_id']
    except:
        pass
    return None

async def fermer_contrat_au_marche(api, contract_id):
    try:
        await api.sell({"sell": contract_id, "price": 0})
        return True
    except:
        return False

# Moteur principal en tâche de fond
async def moteur_trading_background():
    api = DerivAPI(app_id=APP_ID)
    try:
        await api.authorize(TOKEN)
        last_processed_epoch = 0
        active_contract = None
        temps_expiration = None
        logs_list = ["🚀 Connexion établie avec succès sur les serveurs Deriv."]

        while True:
            # Relecture des paramètres configurés sur l'interface graphique
            try:
                with open("bot_config.json", "r") as f:
                    config = json.load(f)
            except:
                config = {"risk": 0.30, "hold": 2, "multiplier": 400}

            # Gestion de la fermeture du contrat (Chrono)
            if active_contract and datetime.now() >= temps_expiration:
                succes = await fermer_contrat_au_marche(api, active_contract)
                if succes:
                    logs_list.append(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] Échéance atteinte. Contrat clôturé avec succès.")
                    active_contract = None
                    temps_expiration = None

            # Collecte du flux M1
            try:
                data = await api.ticks_history({'ticks_history': 'BOOM1000', 'count': 30, 'granularity': 60, 'style': 'candles', 'end': 'latest'})
                if 'candles' in data:
                    df = pd.DataFrame(data['candles'])
                    df.columns = [col.lower() for col in df.columns]
                    is_spike, is_perfect = analyser_anatomie_spike(df)
                    
                    current_epoch = df.iloc[-1]['epoch']
                    
                    if current_epoch != last_processed_epoch and active_contract is None:
                        time_str = datetime.now().strftime('%H:%M:%S')
                        logs_list.append(f"⏳ [{time_str}] [VEILLE] Bougie M1 close analysée.")
                        
                        capital = await recuperer_capital_reel(api)
                        if capital and capital >= MIN_STAKE_DERIV:
                            mise = max(MIN_STAKE_DERIV, capital * config['risk'])
                            
                            if is_perfect:
                                logs_list.append(f"🎯 [{time_str}] SPIKE PARFAIT DÉTECTÉ. Envoi de l'ordre...")
                                cid = await executer_contrat_multdown(api, "BOOM1000", mise, config['multiplier'])
                                if cid:
                                    active_contract = cid
                                    temps_expiration = datetime.now() + timedelta(minutes=config['hold'])
                                    logs_list.append(f"💰 Position ouverte avec succès ! ID: {cid}")
                        
                        last_processed_epoch = current_epoch
            except:
                pass

            # Mise à jour du statut pour l'affichage web
            solde_actuel = await recuperer_capital_reel(api) or 0.0
            statut_global = {
                "balance": solde_actuel,
                "active_trade": f"MULTDOWN actif (ID: {active_contract})" if active_contract else "Aucun",
                "morphology": "Spike d'épuisement validé 🎯" if is_perfect else "Normal / Recherche...",
                "logs": "\n".join(logs_list[-6:]) # Garder les 6 derniers logs
            }
            with open(STATUS_FILE, "w") as f:
                json.dump(statut_global, f)

            await asyncio.sleep(4)
    except Exception as e:
        with open(STATUS_FILE, "w") as f:
            json.dump({"balance": 0.0, "active_trade": "Erreur", "morphology": "N/A", "logs": f"❌ Erreur de connexion : {e}"}, f)
    finally:
        await api.clear()

# =====================================================================
# 3. INTERFACE GRAPHIQUE (STREAMLIT FRONT-END)
# =====================================================================
st.title("📈 Tableau de Bord Interactif — Robot Boom 1000")
st.markdown("Gestion automatisée par analyse anatomique des pics d'épuisement.")

# Panneau latéral de contrôle des risques
st.sidebar.header("⚙️ Configuration Stratégique")
st.sidebar.markdown("Ajustez vos paramètres en direct :")

risk_pct = st.sidebar.slider("Compounding / Risque par trade (%)", 10, 50, 30, step=5)
hold_min = st.sidebar.slider("Rétention en position (Minutes)", 1, 5, 2)
multiplier_choice = st.sidebar.selectbox("Levier / Multiplicateur", [100, 200, 400], index=2)

if st.sidebar.button("💾 Enregistrer les Modifications"):
    with open("bot_config.json", "w") as f:
        json.dump({"risk": risk_pct / 100, "hold": hold_min, "multiplier": multiplier_choice}, f)
    st.sidebar.success("Paramètres synchronisés !")

# Bouton d'arrière plan pour démarrer la machine invisible
if 'bot_loop_started' not in st.session_state:
    st.session_state['bot_loop_started'] = True
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(moteur_trading_background())
    except:
        pass

# Lecture des données calculées par le moteur de fond
try:
    with open(STATUS_FILE, "r") as f:
        data_web = json.load(f)
except:
    data_web = {"balance": 0.0, "active_trade": "Chargement...", "morphology": "N/A", "logs": "Initialisation..."}

# Affichage des Metrics en colonnes
c1, c2, c3 = st.columns(3)
with c1:
    st.metric(label="💳 Solde Réel de votre compte", value=f"{data_web['balance']:.2f} $")
with c2:
    st.metric(label="🚀 État de la position", value=str(data_web['active_trade']))
with c3:
    st.metric(label="🎯 Analyse Morphologique", value=str(data_web['morphology']))

st.markdown("---")

# Zone d'affichage des journaux de bord (Console en direct)
st.subheader("📋 Journal d'activité du serveur (Logs)")
st.code(data_web['logs'], language="text")

# Auto-refresh de la page toutes les 5 secondes pour mettre à jour l'affichage
time.sleep(5)
st.rerun()
