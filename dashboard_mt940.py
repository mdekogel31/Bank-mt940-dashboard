import streamlit as st
import pandas as pd
import mt940
import plotly.express as px
import json
import os

#streamlit run abnamro_mt3.py

st.set_page_config(page_title="Bank Dashboard", layout="wide")

st.title("🏦 MT940 Bankbestand Dashboard")
st.write("welk `.sta` of `.txt` MT940 bestand wil je analyseren.")


BESTAND_NAAM = "regels.json"
STANDAARD_REGELS = {"Energie": ["zonneplan"], "Inkomsten": ["Pensioen"]}

# --- 1. FUNCTIES VOOR BESTANDSBEHEER (Met utf-8-sig) ---
def laad_regels():
    if not os.path.exists(BESTAND_NAAM):
        with open(BESTAND_NAAM, "w", encoding="utf-8-sig") as f:
            json.dump(STANDAARD_REGELS, f, indent=4, ensure_ascii=False)
        return STANDAARD_REGELS
    with open(BESTAND_NAAM, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def sla_regels_op(regels):
    with open(BESTAND_NAAM, "w", encoding="utf-8-sig") as f:
        json.dump(regels, f, indent=4, ensure_ascii=False)
    st.rerun()

# 2A. INITIALISATIE ---
rules = laad_regels()

# 2B Sorteer zowel de categorieën (keys) als de binnenste lijsten (values)

rules = {
    categorie: sorted(zoekwoorden) 
    for categorie, zoekwoorden in sorted(rules.items())
}


# --- 3. INTERFACE IN DE SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Categorieën Beheren ")
    st.write("Wijzig zoektermen. Update dashboard automatisch.")
    
    # --- DEEL A: REGEL TOEVOEGEN ---
    st.subheader("➕ Toevoegen")
    
    bestaande_cat = list(rules.keys())
    opties = ["-- Nieuwe Categorie --"] + bestaande_cat
    geselecteerde_cat = st.selectbox("Kies categorie:", opties, key="sb_Kies_cat")
    
    if geselecteerde_cat == "-- Nieuwe Categorie --":
        nieuwe_cat = st.text_input("Naam nieuwe categorie:", key="sb_nieuwe_cat").strip()
        doel_categorie = nieuwe_cat
    else:
        doel_categorie = geselecteerde_cat

    nieuwe_zoekterm = st.text_input("Typ zoekterm (bijv. 'pwn'):", key="sb_zoekterm").strip()

    if st.button("Voeg toe", type="primary", key="sb_btn_voegtoe"):
        if not doel_categorie or not nieuwe_zoekterm:
            st.error("Vul beide velden in.")
        else:
            if doel_categorie not in rules:
                rules[doel_categorie] = []
            
            if nieuwe_zoekterm.lower() not in [t.lower() for t in rules[doel_categorie]]:
                rules[doel_categorie].append(nieuwe_zoekterm)
                sla_regels_op(rules)
            else:
                st.warning("Bestaat al!")

    st.markdown("---") # Scheidingslijntje in de sidebar

    # --- DEEL B: REGELS BEKIJKEN & VERWIJDEREN ---
    st.subheader("📋 Huidige regels")
    
    if not rules:
        st.info("Geen regels aanwezig.")
    else:
        for categorie, zoektermen in list(rules.items()):
            # Uitklapmenu per categorie IN de sidebar
            with st.expander(f"📁 {categorie} ({len(zoektermen)})"):
                for term in zoektermen:
                    col_term, col_btn = list(st.columns([3, 1]))
                    col_term.write(f"`{term}`")
                    
                    # Compact prullenbakje
                    if col_btn.button("🗑️", key=f"sb_del_{categorie}_{term}"):
                        rules[categorie].remove(term)
                        if not rules[categorie]:
                            del rules[categorie]
                        sla_regels_op(rules)

# 1. Functie voor automatische categorisatie
def categoriseer_transactie(row):
    # Als het inkomsten zijn, categoriseer als Inkomsten
#     if row["Bedrag"] > 0:
#         return "Inkomsten / Omzet"
    
    # Maak tekst klein voor makkelijk zoeken
    omschrijving = str(row["Omschrijving"]).lower()
    naam = str(row["Naam"]).lower()
    code = str(row["Code"]).upper()
    
    # Check eerst op mislukte incasso's (zoals N426)
    if "426" in code or "storno" in omschrijving or "stornering" in omschrijving:
        return "Mislukte Incasso / Storno"
        
    # Categorieën en bijbehorende trefwoorden
    
    
    for categorie, trefwoorden in rules.items():
        for trefwoord in trefwoorden:
            if trefwoord in omschrijving or trefwoord in naam:
                return categorie
                
    if row["Bedrag"] > 0:
        return "Overige Inkomsten"
    else:
        return "Overige Uitgaven"

# 2. File Uploader component
uploaded_file = st.file_uploader("Kies een MT940 bestand", type=["sta", "txt"])

if uploaded_file is not None:
    # Tijdelijk opslaan om te kunnen parsen
    with open("temp_bank_file.sta", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    try:
        transactions = mt940.parse("temp_bank_file.sta")
        data = []
        for tx in transactions:
            data.append({
                "Datum": pd.to_datetime(tx.data.get("date")),
                "Bedrag": float(tx.data.get("amount").amount),
                "Valuta": tx.data.get("amount").currency,
                "Tegenrekening": tx.data.get("account_number"),
                "Naam": tx.data.get("applicant_name"),
                "Omschrijving": tx.data.get("transaction_details"),
                "Code": tx.data.get("status") if tx.data.get("status") else ""
            })
        
        df = pd.DataFrame(data)
        df["Type"] = df["Bedrag"].apply(lambda x: "Inkomsten" if x > 0 else "Uitgaven")
        
        # Pas de categorisatie toe op elke rij
        df["Categorie"] = df.apply(categoriseer_transactie, axis=1)
        
        # 3. KPI / Statistieken Blokken
        totaal_instroom = df[df["Bedrag"] > 0]["Bedrag"].sum()
        totaal_uitstroom = df[df["Bedrag"] < 0]["Bedrag"].sum()
        netto_resultaat = totaal_instroom + totaal_uitstroom
        
        #Formatteer met een tijdelijk uniek teken X
        geformatteerd_totaalin = f"{totaal_instroom:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        geformatteerd_totaaluit = f"{totaal_uitstroom:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        geformatteerd_netto = f"{netto_resultaat:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
       
       # 2. Plaats het in je metric
              
        col1, col2, col3 = st.columns(3)
        col1.metric("Totale Inkomsten", f"€ {geformatteerd_totaalin}")
        col2.metric("Totale Uitgaven", f"€ {geformatteerd_totaaluit}")
        col3.metric("Netto Resultaat", f"€ {geformatteerd_netto}")
        

        
        # --- ALERT VOOR MISLUKTE INCASSO'S (N426) ---
        mislukte_incassos = df[df["Categorie"] == "Mislukte Incasso / Storno"]
        if not mislukte_incassos.empty:
            st.error(f"⚠️ Let op: Er zijn {len(mislukte_incassos)} mislukte incasso's of storno's gevonden!")
            st.dataframe(mislukte_incassos[["Datum", "Naam", "Bedrag", "Omschrijving"]], use_container_width=True)
        
        # 4A. Grafieken Sectie
        st.subheader("Visualisaties & Kostenverdeling")
       
        
        
        # Transactieverloop
        df_gesorteerd = df.sort_values("Datum")
        fig_tijd = px.line(df_gesorteerd, x="Datum", y="Bedrag", title="Transactieverloop door de tijd", markers=True)
        st.plotly_chart(fig_tijd, use_container_width=True)
            
        
        # 4B. Grafieken Sectie
        st.subheader("Visualisaties Inkomsten & Kostenverdeling")
        gcol1, gcol2 = st.columns(2)
        
        with gcol1:
            # Uitgaven per categorie (Inkomsten uitsluiten voor een zuiver beeld van de kosten)
            df_uitgaven = df[df["Bedrag"] >0]
            # Maak bedragen positief voor de cirkeldiagram
            df_uitgaven_pos = df_uitgaven.copy()
            df_uitgaven_pos["Bedrag_Positief"] = df_uitgaven_pos["Bedrag"].abs()
            
            fig_pie_cat = px.pie(
                df_uitgaven_pos, 
                values="Bedrag_Positief", 
                names="Categorie", 
                title="Inkomsten per Categorie",
                hole=0.4
            )
            
            fig_pie_cat.update_traces(
                textinfo="percent+value",
                texttemplate="%{label}<br>%{percent}<br>€%{value:.0f}",
                hovertemplate="%{label}<br>€%{value:.2f}<br>%{percent}"
                )
            
            # === DIT IS DE EXTRA REGEL ===
            # De eerste letter (',') is het decimaal-teken, de tweede ('.') is het duizendtal-teken
            fig_pie_cat.update_layout(separators=",.")
            # =============================
            
            st.plotly_chart(fig_pie_cat, use_container_width=True)
            
        with gcol2:
            # Uitgaven per categorie (Inkomsten uitsluiten voor een zuiver beeld van de kosten)
            df_uitgaven = df[df["Bedrag"] < 0]
            # Maak bedragen positief voor de cirkeldiagram
            df_uitgaven_pos = df_uitgaven.copy()
            df_uitgaven_pos["Bedrag_Positief"] = df_uitgaven_pos["Bedrag"].abs()
            
            fig_pie_cat = px.pie(
                df_uitgaven_pos, 
                values="Bedrag_Positief", 
                names="Categorie", 
                title="Uitgaven per Categorie",
                hole=0.4
            )
            
            # HIER: Dit zorgt ervoor dat er in en rondom de taartpunten een €-teken komt te staan.
            # :.2f geeft 2 decimalen achter de komma. 0f geeft hele euro's
            
            fig_pie_cat.update_traces(
                textinfo="percent+value",
                texttemplate="%{label}<br>%{percent}<br>€%{value:.0f}",
                hovertemplate="%{label}<br>€%{value:.2f}<br>%{percent}"
                )

            # === DIT IS DE EXTRA REGEL ===
            # De eerste letter (',') is het decimaal-teken, de tweede ('.') is het duizendtal-teken
            fig_pie_cat.update_layout(separators=",.")
            # =============================
            
            st.plotly_chart(fig_pie_cat, use_container_width=True)
            
        # 5. Transactie overzicht met Categorie Filter
        st.subheader("Alle Transacties")
        
        # Filter opties op het dashboard
        all_categories = ["Alle"] + list(df["Categorie"].unique())
        selected_cat = st.selectbox("Filter op Categorie:", all_categories)
        
        if selected_cat != "Alle":
            df_filtered = df[df["Categorie"] == selected_cat]
        else:
            df_filtered = df
            
        st.dataframe(df_filtered.sort_values(by="Datum", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"Er ging iets mis bij het parsen of categoriseren: {e}")
