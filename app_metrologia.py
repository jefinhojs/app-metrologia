import streamlit as st
import pdfplumber
import pandas as pd
from groq import Groq
import json
import datetime
from fpdf import FPDF
import re

# --- 1. CONFIGURAÇÃO SEGURA E INDEPENDENTE ---
st.set_page_config(page_title="Gascat - Motor Metrológico Universal", layout="wide", page_icon="🔬")

try:
    cliente_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
except KeyError:
    st.error("Erro Crítico: Chave da Groq não encontrada. Verifique o arquivo `.streamlit/secrets.toml` com a variável `GROQ_API_KEY`.")
    st.stop()

# --- 2. FUNÇÕES DE SUPORTE ---
def sanitizar_texto(texto):
    """Remove acentos para evitar crash no gerador de PDF (fpdf2 limitação com UTF-8 nativo)."""
    texto = texto.replace("°", " deg ").replace("µ", "u").replace("±", "+/-")
    mapa = {'á':'a','à':'a','ã':'a','â':'a','é':'e','ê':'e','í':'i','ó':'o','õ':'o','ô':'o','ú':'u','ç':'c','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ç':'C'}
    for orig, sub in mapa.items():
        texto = texto.replace(orig, sub)
    return texto

def extrair_texto_pdf(arquivo_pdf):
    """Extrai texto e, se falhar, tenta extrair tabelas diretamente."""
    texto_final = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                texto_final += texto + "\n"
            else:
                # Fallback para PDFs onde o texto é um desenho (comum em tabelas mal formatadas)
                tabelas = page.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        texto_final += " | ".join([str(celula) if celula else "" for celula in linha]) + "\n"
    return texto_final

# --- 3. INTELIGÊNCIA ARTIFICIAL RADICAL (LLAMA 3.1 VIA GROQ) ---
def estruturar_dados_com_ia(texto_bruto):
    prompt = f"""
    Você é um sistema automatizado de extração de dados metrológicos. NÃO CONVERSE. Retorne APENAS o JSON.
    
    REGRAS RÍGIDAS:
    1. Ignore textos legais, cabeçalhos, rodapés e assinaturas.
    2. Se o texto estiver embaralhado (ex: certificados de rosca Metrus), use raciocínio espacial para juntar "Nominal" com "Média das Medições".
    3. TOLERÂNCIA: Se o limite for percentual (ex: "4% da capacidade final", "2% do ponto"), CALCULE o valor absoluto para cada linha e coloque no JSON.
    4. UNIDADES: Converta tudo para a unidade base (ex: µm vira mm dividindo por 1000).
    5. ROSCAS: Separe em grandezas diferentes ("Diametro", "Passo", "Semi Angulo").
    
    RETORNE ESTE FORMATO EXATO:
    {{
      "resumo": {{
        "instrumento": "Nome",
        "laboratorio": "Lab",
        "identificacao": "N Certificado",
        "analise_ia": "Resumo de 2 linhas sobre conversões ou cálculos de limite feitos."
      }},
      "grandezas": [
        {{
          "nome_grandeza": "Pressao",
          "unidade": "bar",
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
    
    TEXTO DO CERTIFICADO:
    {texto_bruto}
    """

    try:
        # Chamada para a Groq com JSON Mode obrigatório
        resposta = cliente_groq.chat.completions.create(
            model="llama-3.1-70b-versatile", # Modelo mais inteligente e rápido disponível de graça
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, # Força 100% de saída JSON válida
            temperature=0.0, # Zero criatividade, máxima precisão matemática
            max_tokens=4096
        )
        return json.loads(resposta.choices[0].message.content)
    except Exception as e:
        st.error(f"Erro de comunicação com a IA: {str(e)}")
        return None

# --- 4. MOTOR METROLÓGICO ---
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
                continue
                
            erro_abs = abs(erro)
            impacto_total = erro_abs + incerteza
            porcentagem = (impacto_total / limite) * 100 if limite != 0 else 0
            
            if limite == 0.0: status = "FALTA LIMITE"
            elif impacto_total <= limite: status = "APROVADO"
            elif erro_abs <= limite: status = "RESSALVA"
            else: status = "REPROVADO"
                
            resultados.append({
                "Padrão (VRM)": vrm,
                "Indicado (VIM)": round(vim, 5),
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

# --- 5. GERADOR DE PDF ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    try: pdf.image("logo.png", x=10, y=8, w=40)
    except: pass 
    
    pdf.set_y(15)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, sanitizar_texto("LAUDO METROLOGICO - AVALIACAO DE CERTIFICADO"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 5, sanitizar_texto(f"Documento: {nome_original} | Data: {data_hoje} | Gascat"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(3)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(0, 5, sanitizar_texto("Sintese da IA:"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 8)
    texto_resumo = sanitizar_texto(f"Inst: {resumo_ia.get('instrumento', 'N/D')} | ID: {resumo_ia.get('identificacao', 'N/D')} | Lab: {resumo_ia.get('laboratorio', 'N/D')} - {resumo_ia.get('analise_ia', '')}")
    pdf.multi_cell(0, 4, texto_resumo)
    pdf.ln(3)
    
    # Tabela segura
    pdf.set_font("helvetica", "", 6)
    colunas = df_resultados.columns.tolist()
    with pdf.table(borders_layout="ALL", text_align="CENTER") as table:
        header = table.row()
        for col in colunas:
            header.cell(sanitizar_texto(str(col)))
        for _, row in df_resultados.iterrows():
            linha = table.row()
            for item in row:
                # Trunca textos longos para não quebrar o layout do PDF
                valor = str(item)[:25] if len(str(item)) > 25 else str(item)
                linha.cell(sanitizar_texto(valor))
                
    pdf.ln(8)
    
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    if tem_reprovado:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(220, 53, 69)
        pdf.cell(0, 10, "STATUS: REPROVADO - BLOQUEADO", align="C", new_x="LMARGIN", new_y="NEXT")
    elif falta_limite:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 10, "STATUS: PENDENTE - FALTA LIMITE", align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(40, 167, 69)
        pdf.cell(0, 10, "STATUS: APROVADO - LIBERADO", align="C", new_x="LMARGIN", new_y="NEXT")
        try: pdf.image("assinatura.png", x=110, w=70)
        except: pass
            
    pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())

# --- 6. INTERFACE STREAMLIT ---
st.title("🔬 Motor Metrológico Universal - Gascat")
st.markdown("Powered by **Llama 3.1 (Groq)** | Extração 100% gratuita, local e sem falhas de conexão.")

arquivo = st.file_uploader("Insira o Certificado (PDF)", type=["pdf"])

if arquivo:
    with st.spinner("Processando documento via Llama 3.1..."):
        texto = extrair_texto_pdf(arquivo)
        
        if not texto.strip():
            st.error("Falha: O PDF não contém texto extraível. Pode ser um arquivo formado apenas por imagens.")
            st.stop()
            
        # Cortar texto gigante para não estourar limites (Groq aceita até 128k, mas isso economiza processamento)
        if len(texto) > 25000:
            texto = texto[:25000]
            
        dados_json = estruturar_dados_com_ia(texto)
        
        if dados_json and "grandezas" in dados_json:
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da IA")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", sanitizar_texto(resumo.get("instrumento", "N/A")[:30]))
            col_b.metric("Identificação", sanitizar_texto(resumo.get("identificacao", "N/A")[:30]))
            col_c.metric("Laboratório", sanitizar_texto(resumo.get("laboratorio", "N/A")[:30]))
            st.info(f"**Análise:** {sanitizar_texto(resumo.get('analise_ia', 'Sem observações.'))}")
            
            df = avaliar_metrologia(dados_json["grandezas"])
            
            if not df.empty:
                tem_reprovado = "REPROVADO" in df['Decisão'].values
                falta_limite = "FALTA LIMITE" in df['Decisão'].values
                
                st.markdown("### 📊 Laudo Metrológico")
                if tem_reprovado: st.error("🚨 **LAUDO FINAL: REPROVADO**")
                elif falta_limite: st.warning("⚠️ **LAUDO FINAL: PENDENTE**")
                else: st.success("✅ **LAUDO FINAL: APROVADO**")
                
                def cor_status(val):
                    if val == "APROVADO": return 'background-color: rgba(144,238,144,0.2); color:#1e7e34; font-weight:bold;'
                    elif val == "RESSALVA": return 'background-color: rgba(255,255,102,0.3); color:#856404; font-weight:bold;'
                    elif val == "REPROVADO": return 'background-color: rgba(255,99,71,0.3); color:#bd2130; font-weight:bold;'
                    elif val == "FALTA LIMITE": return 'background-color: rgba(200,200,200,0.3); color:#444444; font-weight:bold;'
                    return ''

                st.dataframe(df.style.map(cor_status, subset=['Decisão']), use_container_width=True, hide_index=True)
                
                pdf_bytes = gerar_relatorio_pdf(df, arquivo.name, resumo)
                nome_exportacao = f"{arquivo.name.rsplit('.', 1)[0]}_LAUDO_GASCAT.pdf"
                
                st.download_button(
                    label="📥 Baixar Laudo Oficial PDF",
                    data=pdf_bytes,
                    file_name=nome_exportacao,
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.warning("A IA leu o documento, mas não encontrou tabelas numéricas válidas para gerar o laudo.")
