import streamlit as st
import pdfplumber
import pandas as pd
from groq import Groq
import json
import datetime
from fpdf import FPDF
import time

# --- 1. CONFIGURAÇÃO SEGURA E INDEPENDENTE ---
st.set_page_config(page_title="Gascat - Motor Metrológico Universal", layout="wide", page_icon="🔬")

# Captura uma lista de chaves (Fallback Router)
try:
    # Tenta pegar a lista de chaves; se não existir, cria uma lista com a chave única antiga
    CHAVES_API = st.secrets.get("GROQ_API_KEYS", [st.secrets.get("GROQ_API_KEY")])
    if not CHAVES_API or None in CHAVES_API:
        raise KeyError
except KeyError:
    st.error("Erro Crítico: Configure o arquivo `.streamlit/secrets.toml` com a variável `GROQ_API_KEYS = ['chave1', 'chave2']`.")
    st.stop()

# --- 2. FUNÇÕES DE SUPORTE ---
def sanitizar_texto(texto):
    texto = str(texto).replace("°", " deg ").replace("µ", "u").replace("±", "+/-")
    mapa = {'á':'a','à':'a','ã':'a','â':'a','é':'e','ê':'e','í':'i','ó':'o','õ':'o','ô':'o','ú':'u','ç':'c','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ç':'C'}
    for orig, sub in mapa.items():
        texto = texto.replace(orig, sub)
    return texto

def extrair_texto_pdf(arquivo_pdf):
    texto_final = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                texto_final += texto + "\n"
            else:
                tabelas = page.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        texto_final += " | ".join([str(celula) if celula else "" for celula in linha]) + "\n"
    return texto_final

# --- 3. INTELIGÊNCIA ARTIFICIAL (COM ROTEAMENTO DE FALLBACK) ---
def estruturar_dados_com_ia(texto_bruto, criterio_usuario):
    prompt = f"""
    Você é um sistema automatizado de extração de dados metrológicos. NÃO CONVERSE. Retorne APENAS o JSON.
    
    REGRAS RÍGIDAS:
    1. Ignore textos legais, cabeçalhos e assinaturas.
    2. TOLERÂNCIA: Se o usuário definiu uma tolerância global ({criterio_usuario}), aplique-a no campo "limite" de TODOS os pontos. Caso seja 0.0, extraia o limite do texto.
    3. UNIDADES: Converta tudo para a unidade base.
    
    RETORNE ESTE FORMATO EXATO:
    {{
      "resumo": {{
        "instrumento": "Nome",
        "laboratorio": "Lab",
        "identificacao": "N Certificado",
        "analise_ia": "Resumo rápido."
      }},
      "grandezas": [
        {{
          "nome_grandeza": "Pressao",
          "unidade": "bar",
          "pontos": [
            {{"vrm": 0.0, "vim": 0.0, "erro": 0.0, "incerteza": 0.0, "limite": {criterio_usuario if criterio_usuario > 0 else 0.0}}}
          ]
        }}
      ]
    }}
    
    TEXTO:
    {texto_bruto}
    """

    ultimo_erro = None
    # Motor de Fallback (Rotaciona as chaves se os tokens acabarem)
    for index, chave in enumerate(CHAVES_API):
        # Modifique APENAS este bloco dentro da função estruturar_dados_com_ia
        try:
            cliente_groq = Groq(api_key=chave)
            resposta = cliente_groq.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, 
                temperature=0.0, 
                max_tokens=1000 # <--- MUDANÇA CRÍTICA AQUI (De 4096 para 1000)
            )
            return json.loads(resposta.choices[0].message.content)
        
        except Exception as e:
            erro_str = str(e).lower()
            # Se for erro de limite de requisição, tenta a próxima chave
            if "rate limit" in erro_str or "429" in erro_str or "capacity" in erro_str:
                ultimo_erro = e
                continue 
            else:
                st.error(f"Erro de processamento da IA: {str(e)}")
                return None
                
    st.error(f"🚨 Falha Crítica: Todas as {len(CHAVES_API)} chaves esgotaram seus limites. Último erro: {ultimo_erro}")
    return None
        
# --- 4. MOTOR METROLÓGICO ---
def avaliar_metrologia(grandesas, criterio_usuario):
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
                # Força o critério do usuário na validação final
                limite = float(criterio_usuario) if criterio_usuario > 0.0 else float(p.get('limite', 0))
            except ValueError:
                continue
                
            erro_abs = abs(erro)
            impacto_total = erro_abs + incerteza
            porcentagem = (impacto_total / limite) * 100 if limite != 0 else 0
            
            # Avaliação rigorosa: $$ |Erro| + U \leq Limite $$
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

# --- 5. GERADOR DE PDF (MANTIDO INTACTO) ---
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
    
    pdf.set_font("helvetica", "", 6)
    colunas = df_resultados.columns.tolist()
    with pdf.table(borders_layout="ALL", text_align="CENTER") as table:
        header = table.row()
        for col in colunas:
            header.cell(sanitizar_texto(str(col)))
        for _, row in df_resultados.iterrows():
            linha = table.row()
            for item in row:
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
st.markdown("Powered by **Llama 3.3 (Groq)** | Extração com Fallback Automático.")

# Nova Área de Configuração Acima do Upload
st.markdown("### ⚙️ Parâmetros de Calibração")
criterio_usuario = st.number_input(
    "Critério de Aceitação (Tolerância do Instrumento):", 
    min_value=0.0, 
    value=0.0, 
    format="%.4f", 
    help="Se definido maior que 0, este valor substituirá qualquer limite encontrado no certificado. Se deixar 0.0, a IA tentará extrair a tolerância do PDF automaticamente."
)

st.markdown("---")
arquivo = st.file_uploader("Insira o Certificado (PDF)", type=["pdf"])

if arquivo:
    with st.spinner("Processando documento... (Testando roteamento de API)"):
        texto = extrair_texto_pdf(arquivo)
        
        if not texto.strip():
            st.error("Falha: O PDF não contém texto extraível.")
            st.stop()
            
        # Modifique APENAS esta validação de tamanho antes de chamar a IA
        if len(texto) > 10000: # <--- Reduzido de 25000 para 10000
            texto = texto[:10000]
            
        # Passando o critério para a IA
        dados_json = estruturar_dados_com_ia(texto, criterio_usuario)
            
        # Passando o critério para a IA
        dados_json = estruturar_dados_com_ia(texto, criterio_usuario)
        
        if dados_json and "grandezas" in dados_json:
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da IA")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", sanitizar_texto(resumo.get("instrumento", "N/A")[:30]))
            col_b.metric("Identificação", sanitizar_texto(resumo.get("identificacao", "N/A")[:30]))
            col_c.metric("Laboratório", sanitizar_texto(resumo.get("laboratorio", "N/A")[:30]))
            st.info(f"**Análise:** {sanitizar_texto(resumo.get('analise_ia', 'Sem observações.'))}")
            
            # Passando o critério para o motor matemático
            df = avaliar_metrologia(dados_json["grandezas"], criterio_usuario)
            
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
