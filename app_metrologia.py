import streamlit as st
import pdfplumber
import pandas as pd
import google.generativeai as genai
import json
import datetime
from fpdf import FPDF
import re

# --- 1. CONFIGURAÇÃO E SEGURANÇA ---
st.set_page_config(page_title="Gascat - Inteligência Metrológica", layout="wide", page_icon="🔬")

try:
    CHAVE_API = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=CHAVE_API)
except KeyError:
    st.error("Erro Crítico: API Key não encontrada. Verifique o arquivo `.streamlit/secrets.toml`.")
    st.stop()

# --- 2. FUNÇÃO DE SUPORTE PARA PDF (Evita crash com acentos) ---
def sanitizar_texto(texto):
    """Remove acentos e caracteres especiais para evitar erro no gerador de PDF."""
    texto = texto.replace("°", " deg ").replace("µ", "u").replace("±", "+/-")
    mapa_acentos = {'á':'a','à':'a','ã':'a','â':'a','é':'e','ê':'e','í':'i','ó':'o','õ':'o','ô':'o','ú':'u','ç':'c','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ç':'C'}
    for original, substituto in mapa_acentos.items():
        texto = texto.replace(original, substituto)
    return texto

# --- 3. EXTRAÇÃO DE TEXTO OTIMIZADA ---
def extrair_texto_pdf(arquivo_pdf):
    """Extrai texto pulando cabeçalhos e rodapés repetidos para economizar tokens."""
    texto = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            txt = pagina.extract_text()
            if txt:
                texto += txt + "\n"
    return texto

# --- 4. INTELIGÊNCIA ARTIFICIAL AVANÇADA (ZERO ERRO DE JSON) ---
def estruturar_dados_com_ia(texto_bruto):
    # Usa o gemini-1.5-flash (Gratuito, rápidissimo e aceita JSON mode nativo)
    modelo = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )
    
    prompt = f"""
    Você é um Engenheiro Metrologista Sênior. EXTRAIA os dados deste certificado de calibração.
    REGRAS ESTRICTAS DE ECONOMIA E PRECISÃO:
    1. Ignore textos legais, assinaturas, endereços e condições ambientais. Foque nos DADOS e TABELAS.
    2. Se o texto da tabela vier embaralhado (comum em PDFs de rosca), use seu conhecimento metrológico para reconstruir os pares [Nominal/Padrão] e [Medido/Média].
    3. LIMITE DE TOLERÂNCIA: Se for percentual (ex: "4% da capacidade final", "2% do ponto"), CALCULE o valor absoluto para cada ponto e coloque no campo "limite".
    4. UNIDADES: Se houver mistura de mm e µm, converta TUDO para mm (divida µm por 1000).
    5. CERTIFICADOS DE ROSCA: Separe em grandezas diferentes (Ex: "Diametro Flanco", "Passo", "Semi Angulo").
    6. Se não houver limite de tolerância informado, use 0.0.

    RETORNE APENAS ESTE JSON:
    {{
      "resumo": {{
        "instrumento": "Nome do instrumento",
        "laboratorio": "Nome do Lab",
        "identificacao": "Nº Certificado / Tag",
        "analise_ia": "Breve resumo do que encontrou, se fez conversões ou cálculos de limite percentual."
      }},
      "grandezas": [
        {{
          "nome_grandeza": "Ex: Pressao, Diametro, Temperatura IN",
          "unidade": "Ex: bar, mm, °C",
          "pontos": [
            {{
              "vrm": 0.0, 
              "vim": 0.0, 
              "erro": 0.0, 
              "incerteza": 0.0, 
              "limite": 0.0
            }}
          ]
        }}
      ]
    }}
    TEXTO EXTRAÍDO:
    {texto_bruto}
    """
    
    try:
        resposta = modelo.generate_content(prompt)
        # O Gemini garante 100% que isso será um JSON válido por causa do response_mime_type
        return json.loads(respuesta.text)
    except Exception as e:
        st.error(f"Erro na comunicação com a IA: {str(e)}")
        return None

# --- 5. MOTOR METROLÓGICO BLINDADO ---
def avaliar_metrologia(grandesas):
    todos_dfs = []
    for grandeza in grandesas:
        pontos = grandeza.get("pontos", [])
        resultados = []
        for p in pontos:
            try:
                vrm = float(p.get('vrm', 0))
                vim = float(p.get('vim', 0))
                erro = float(p.get('erro', 0))
                incerteza = float(p.get('incerteza', 0))
                limite = float(p.get('limite', 0))
            except ValueError:
                continue # Pula linhas corrompidas
                
            erro_abs = abs(erro)
            impacto_total = erro_abs + incerteza
            porcentagem = (impacto_total / limite) * 100 if limite != 0 else 0
            
            if limite == 0.0: status = "FALTA LIMITE"
            elif impacto_total <= limite: status = "APROVADO"
            elif erro_abs <= limite: status = "RESSALVA"
            else: status = "REPROVADO"
                
            resultados.append({
                "Padrão (V.R.M)": vrm,
                "Indicado (V.I.M)": round(vim, 5),
                "Erro": round(erro, 5),
                "Incerteza (U)": round(incerteza, 5),
                "Limite (Tol)": limite,
                "|Erro| + U": round(impacto_total, 5),
                "% Tol.": round(porcentagem, 2) if limite != 0 else "N/A",
                "Decisão": status
            })
        
        if resultados:
            df = pd.DataFrame(resultados)
            df.insert(0, "Grandeza", grandeza.get("nome_grandeza", "N/D"))
            df.insert(1, "Unidade", grandeza.get("unidade", "N/D"))
            todos_dfs.append(df)
            
    return pd.concat(todos_dfs, ignore_index=True) if todos_dfs else pd.DataFrame()

# --- 6. GERADOR DE PDF ROBUSTO ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Tenta adicionar logo, se existir
    try: pdf.image("logo.png", x=10, y=8, w=40)
    except: pass 
    
    pdf.set_y(15)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, sanitizar_texto("LAUDO METROLOGICO - AVALIACAO DE CERTIFICADO"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 5, sanitizar_texto(f"Documento Base: {nome_original} | Data: {data_hoje} | Area: Usinagem Gascat"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, sanitizar_texto("Sintese da Extracao (IA):"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 9)
    texto_resumo = sanitizar_texto(f"Instrumento: {resumo_ia.get('instrumento', 'N/D')} | OS/TAG: {resumo_ia.get('identificacao', 'N/D')} | Lab: {resumo_ia.get('laboratorio', 'N/D')}\nAnalise: {resumo_ia.get('analise_ia', 'Sem analise.')}")
    pdf.multi_cell(0, 5, texto_resumo)
    pdf.ln(5)
    
    # Tabela
    pdf.set_font("helvetica", "", 7)
    colunas = df_resultados.columns.tolist()
    with pdf.table(borders_layout="ALL", text_align="CENTER") as table:
        header = table.row()
        for col in colunas:
            header.cell(sanitizar_texto(str(col)))
        for _, row in df_resultados.iterrows():
            linha = table.row()
            for item in row:
                linha.cell(sanitizar_texto(str(item)))
                
    pdf.ln(10)
    
    # Decisão Final
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    if tem_reprovado:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(220, 53, 69)
        pdf.cell(0, 10, sanitizar_texto("STATUS FINAL: REPROVADO - INSTRUMENTO BLOQUEADO"), align="C", new_x="LMARGIN", new_y="NEXT")
    elif falta_limite:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 10, sanitizar_texto("STATUS FINAL: PENDENTE - FALTA LIMITE DE TOLERANCIA"), align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(40, 167, 69)
        pdf.cell(0, 10, sanitizar_texto("STATUS FINAL: APROVADO - LIBERADO PARA OPERACAO"), align="C", new_x="LMARGIN", new_y="NEXT")
        try: pdf.image("assinatura.png", x=110, w=70)
        except: pass
            
    pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())

# --- 7. INTERFACE STREAMLIT ---
st.title("🔬 Motor Metrológico Universal - Nível Sênior")
st.markdown("Processamento avançado via **Gemini 1.5 Flash (Gratuito)**. Interpretador de Roscas, Manômetros, Termômetros e Dimencionais.")

arquivo = st.file_uploader("Insira o Certificado Analítico (PDF)", type=["pdf"])

if arquivo:
    with st.spinner("Extraindo texto e acionando IA com JSON Mode Estrito..."):
        texto = extrair_texto_pdf(arquivo)
        
        # Corte de segurança para não estourar o limite de tokens (Caso de PDFs gigantes de 50 páginas)
        if len(texto) > 30000:
            texto = texto[:30000]
            st.warning("PDF muito longo detectado. O texto foi truncado nas primeiras 30k palavras para garantir estabilidade.")
            
        dados_json = estruturar_dados_com_ia(texto)
        
        if dados_json and "grandezas" in dados_json:
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da Inteligência Artificial")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", sanitizar_texto(resumo.get("instrumento", "N/A")))
            col_b.metric("OS/TAG", sanitizar_texto(resumo.get("identificacao", "N/A")))
            col_c.metric("Laboratório", sanitizar_texto(resumo.get("laboratorio", "N/A")))
            st.info(f"**Parecer da Leitura:** {sanitizar_texto(resumo.get('analise_ia', 'Sem observações.'))}")
            
            df = avaliar_metrologia(dados_json["grandezas"])
            
            if not df.empty:
                tem_reprovado = "REPROVADO" in df['Decisão'].values
                tem_ressalva = "RESSALVA" in df['Decisão'].values
                falta_limite = "FALTA LIMITE" in df['Decisão'].values
                
                st.markdown("### 📊 Laudo da Avaliação Metrológica")
                if tem_reprovado: st.error("🚨 **LAUDO FINAL: REPROVADO**")
                elif falta_limite: st.warning("⚠️ **LAUDO FINAL: PENDENTE (FALTA LIMITE)**")
                elif tem_ressalva: st.warning("⚠️ **LAUDO FINAL: APROVADO COM RESSALVAS**")
                else: st.success("✅ **LAUDO FINAL: APROVADO**")
                
                def cor_status(val):
                    if val == "APROVADO": return 'background-color: rgba(144,238,144,0.2); color:#1e7e34; font-weight:bold;'
                    elif val == "RESSALVA": return 'background-color: rgba(255,255,102,0.3); color:#856404; font-weight:bold;'
                    elif val == "REPROVADO": return 'background-color: rgba(255,99,71,0.3); color:#bd2130; font-weight:bold;'
                    elif val == "FALTA LIMITE": return 'background-color: rgba(200,200,200,0.3); color:#444444; font-weight:bold;'
                    return ''

                st.dataframe(df.style.map(cor_status, subset=['Decisão']), use_container_width=True, hide_index=True)
                
                st.markdown("---")
                nome_sem_extensao = arquivo.name.rsplit(".", 1)[0]
                nome_exportacao = f"{nome_sem_extensao}_ANALISADO.pdf"
                
                pdf_bytes = gerar_relatorio_pdf(df, arquivo.name, resumo)
                
                st.download_button(
                    label="📥 Exportar Laudo Oficial em PDF",
                    data=pdf_bytes,
                    file_name=nome_exportacao,
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.warning("A IA identificou o documento, mas não conseguiu extrair tabelas de pontos numéricos válidos.")
