import streamlit as st
import pandas as pd
import deepl
import re
import html
import time
from io import BytesIO

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Shopify Translator", layout="wide")
st.title("🌍 Shopify Translator Tool")
st.markdown("Load the CSV, write the product handle and translate it with DeepL.")

# --- SIDEBAR (CONFIGURAZIONE) ---
with st.sidebar:
    st.header("Configuration")
    # Puoi mettere qui la chiave fissa se vuoi nasconderla ai colleghi
    # api_key = "LA_TUA_CHIAVE_FISSA" 
    api_key = st.text_input("DeepL API Key", type="password")

    st.info("Instructions:\n1. Load the Shopify Master Export.\n2. Paste the Handles.\n3. Check the preview.\n4. Translate and Download.")


LINK_LANG_MAP = {'it': 'it', 'fr': 'fr', 'de': 'de', 'es': 'es', 'nl': 'nl', 'fi': 'fi'}

def protect_layout(text):
    if not isinstance(text, str): return text
    text = re.sub(r'(\d)\.(\d)', r'\1_DOT_\2', text) # Proteggi 2.0
    text = re.sub(r'<\s*br\s*/?>', '####BR####', text, flags=re.IGNORECASE) # Proteggi <br>
    text = text.replace('####BR####-', '####BR####_DASH_') # Proteggi elenchi
    text = text.replace('####BR#### -', '####BR####_DASH_ ')
    return text

def mask_tags(text):
    if not isinstance(text, str): return text
    pattern = r"(####[\w-]+####|_DOT_|_DASH_)"
    return re.sub(pattern, r'<span translate="no">\1</span>', text)

def unmask_tags(text):
    if not isinstance(text, str): return text
    pattern = r'<span translate="no">(.*?)</span>'
    return re.sub(pattern, r'\1', text)

def restore_layout(text):
    if not isinstance(text, str): return text
    text = text.replace('_DOT_', '.')
    text = text.replace('_DASH_', '-')
    text = text.replace('####BR####', '<br>')
    text = text.replace('<br> _DASH_', '<br>-')
    text = text.replace('<br>_DASH_', '<br>-')
    return text

def localize_links(text, lang_code):
    if not isinstance(text, str): return text
    url_lang = LINK_LANG_MAP.get(lang_code.lower())
    if url_lang:
        url_lang = url_lang.lower()
        text = re.sub(r'(?i)karhu\.com/collections', f'karhu.com/{url_lang}/collections', text)
        text = re.sub(r'(?i)karhu\.com/products', f'karhu.com/{url_lang}/products', text)
    return text

# --- INTERFACCIA UTENTE ---

#  UPLOAD FILE
uploaded_file = st.file_uploader("Load your Product Master Export CSV file from Shopify. ", type=['csv'])

# INPUT HANDLE
handles_input = st.text_area("Write the Product Handle (karhu-example-2-0-white-white)", height=150)

# LOGICA DI RICERCA
if uploaded_file and handles_input:
    # Pulizia input handle
    target_handles = [h.strip() for h in re.split(r'[,\n]', handles_input) if h.strip()]
    
    if st.button(" Search Products"):
        try:
            df = pd.read_csv(uploaded_file, dtype={'Identification': str})
            
            # Cerca ID basati sugli handle
            handle_rows = df[
                (df['Field'] == 'handle') & 
                (df['Default content'].isin(target_handles))
            ]
            
            found_ids = handle_rows['Identification'].unique()
            
            if len(found_ids) == 0:
                st.error("No products found. Check the handles.")
            else:
                # Estrai tutte le righe
                product_df = df[df['Identification'].isin(found_ids)].copy()
                
                # Salva nello "Stato" della app (così non si perde al ricaricamento)
                st.session_state['product_df'] = product_df
                st.session_state['found_ids'] = found_ids
                
                st.success(f"Found {len(found_ids)} products (Total {len(product_df)} rows to process).")
                st.dataframe(product_df.head(10))
                
        except Exception as e:
            st.error(f"Error reading the file: {e}")

# TRADUZIONE
if 'product_df' in st.session_state and api_key:
    st.divider()
    st.subheader("Phase 2: Translation")

    if st.button("Start Translation"):
        translator = deepl.Translator(api_key)
        df_to_process = st.session_state['product_df'].copy()
        
        # Resetta colonne tradotte vecchie
        df_to_process['Translated content'] = None
        df_to_process['Translated content'] = df_to_process['Translated content'].astype(object)
        
        # Barra di progresso
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_rows = len(df_to_process)
        processed = 0
        fields_to_translate = ['body_html', 'meta_description']
        
        for index, row in df_to_process.iterrows():
            processed += 1
            progress_bar.progress(processed / total_rows)
            
            if row['Field'] not in fields_to_translate: continue
            
            locale = str(row['Locale']).lower()
            target_lang = LINK_LANG_MAP.get(locale)
            
            if target_lang and pd.notna(row['Default content']):
                status_text.text(f"Translating...: ID {row['Identification']} ({target_lang})...")
                
                try:
                    # LOGICA "MASKING PREVENTIVO"
                    protected = protect_layout(row['Default content'])
                    masked = mask_tags(protected)
                    
                    result = translator.translate_text(
                        masked, target_lang=target_lang.upper(), tag_handling='html', ignore_tags=['span']
                    )
                    
                    raw = unmask_tags(result.text)
                    restored = restore_layout(raw)
                    final = html.unescape(restored)
                    
                    if row['Field'] == 'body_html':
                        final = localize_links(final, locale)
                        
                    df_to_process.at[index, 'Translated content'] = final
                    
                except Exception as e:
                    st.warning(f"Errore su {locale}: {e}")
                    
        status_text.text("Translation completed!")
        #
        # st.balloons()
        
        # 5. DOWNLOAD
        csv = df_to_process.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="Download the translated CSV",
            data=csv,
            file_name="translated_products_shopify.csv",
            mime="text/csv",
        )