import streamlit as st
import pdfplumber
import pandas as pd
from groq import Groq
import json
import datetime
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Gascat - Motor Metrológico Universal", layout="wide", page_icon="🔬")

try:
    cliente_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
except KeyError:
    st.error("Erro Crítico: Chave da Groq não encontrada.")
    st.stop()

def sanitizar_texto(texto):
    texto = texto.replace("°", " deg ").replace("µ", "u").replace("±", "+/-")
    mapa = {'á':'a','à':'a','ã':'a','â':'a','é':'e','ê':'e','í':'i','ó':'o','õ':'o','ô':'o','ú':'u','ç':'c','Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U','Ç':'C'}
    for orig, sub in mapa.items(): texto = texto.replace(orig, sub)
    return texto

def extrair_texto_pdf(arquivo_pdf):
    texto_final = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto: texto_final += texto + "\n"
            else:
                for tabela in page.extract_tables():
                    for linha in tabela:
                        texto_final += " | ".join([str(celula) if celula else "" for celula in linha]) + "\n"
    return texto_final

# --- 2. INTELIGÊNCIA ARTIFICIAL COM INJEÇÃO DE CONTEXTO ---
def estruturar_dados_com_ia(texto_bruto, limite_informado):
    prompt = f"""
    Você é um sistema automatizado de extração e análise de dados metrológicos industriais. NÃO CONVERSE. Retorne APENAS o JSON.
    
    INFORMAÇÃO CRÍTICA INJETADA PELO ENGENHEIRO:
    O Critério de Aceitação Global para este certificado é de {limite_informado} (na unidade base do instrumento).
    
    REGRAS RÍGIDAS:
    1. Ignore textos legais, cabeçalhos, rodapés e assinaturas.
    2. UNIDADES: Converta tudo para a unidade base (ex: µm vira mm dividindo por 1000).
    3. LIMITE: Preencha TODOS os campos "limite" no JSON estritamente com o valor {limite_informado}. 
    4. ANÁLISE IA: No campo 'analise_ia', faça um resumo inteligente afirmando que a avaliação considerou o limite de {limite_informado} fornecido pelo usuário.
    
    RETORNE ESTE FORMATO EXATO:
    {{
      "resumo": {{
        "instrumento": "Nome",
        "laboratorio": "Lab",
        "identificacao": "N Certificado",
        "analise_ia": "Resumo técnico da avaliação considerando o limite injetado."
      }},
      "grandezas": [
        {{
          "nome_grandeza": "Pressao/Diametro/etc",
          "unidade": "mm",
          "pontos": [
            {{"vrm": 0.0, "vim": 0.0, "erro": 0.0, "incerteza": 0.0, "limite": {limite_informado}}}
          ]
        }}
      ]
    }}
    
    TEXTO DO CERTIFICADO:
    {texto_bruto}
    """
    try:
        resposta = cliente_groq.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, 
            temperature=0.0, 
            max_tokens=4096
        )
        return json.loads(resposta.choices[0].message.content)
    except Exception as e:
        st.error(f"Erro de comunicação com a IA: {str(e)}")
        return None
        
# --- 3. MOTOR METROLÓGICO (AUDITORIA DETERMINÍSTICA) ---
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
                limite = float(p.get('limite', 0)) # Agora a IA já traz o limite correto injetado
            except ValueError:
                continue
                
            erro_abs = abs(erro)
            impacto_total = erro_abs + incerteza
            porcentagem = (impacto_total / limite) * 100 if limite > 0 else 0
            
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
                "% Tol.": round(porcentagem, 1) if limite > 0 else "N/A",
                "Decisão": status
            })
        
        if resultados:
            df = pd.DataFrame(resultados)
            df.insert(0, "Grandeza", grandeza.get("nome_grandeza", "N/D"))
            df.insert(1, "Unidade", grandeza.get("unidade", "N/D"))
            todos_dfs.append(df)
            
    return pd.concat(todos_dfs, ignore_index=True) if todos_dfs else pd.DataFrame()

# --- 4. GERADOR DE PDF ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
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
    texto_resumo = sanitizar_texto(f"Inst: {resumo_ia.get('instrumento', 'N/D')} | ID: {resumo_ia.get('identificacao', 'N/D')} | Lab: {resumo_ia.get('laboratorio', 'N/D')}\nAnalise: {resumo_ia.get('analise_ia', '')}")
    pdf.multi_cell(0, 4, texto_resumo)
    pdf.ln(3)
    
    pdf.set_font("helvetica", "", 7)
    colunas = df_resultados.columns.tolist()
    with pdf.table(borders_layout="ALL", text_align="CENTER") as table:
        header = table.row()
        for col in colunas: header.cell(sanitizar_texto(str(col)))
        for _, row in df_resultados.iterrows():
            linha = table.row()
            for item in row:
                valor = str(item)[:25] if len(str(item)) > 25 else str(item)
                linha.cell(sanitizar_texto(valor))
                
    pdf.ln(8)
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    pdf.set_font("helvetica", "B", 14)
    if tem_reprovado:
        pdf.set_text_color(220, 53, 69)
        pdf.cell(0, 10, "STATUS: REPROVADO - BLOQUEADO", align="C", new_x="LMARGIN", new_y="NEXT")
    elif falta_limite:
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 10, "STATUS: PENDENTE - FALTA LIMITE", align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_text_color(40, 167, 69)
        pdf.cell(0, 10, "STATUS: APROVADO - LIBERADO", align="C", new_x="LMARGIN", new_y="NEXT")
            
    pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())

# --- 5. INTERFACE STREAMLIT ---
st.title("🔬 Motor Metrológico Universal - Gascat")
st.markdown("Avaliação de Certificados com Prompt Ciente de Contexto (ISO 14253-1)")

st.sidebar.header("⚙️ Controle de Critério")
st.sidebar.markdown("Defina o limite antes de enviar o PDF. A IA fará a leitura já sabendo dessa regra.")
# Campo para injetar o limite na IA
limite_usuario = st.sidebar.number_input("Critério de Aceitação (mm/bar/etc)", min_value=0.000, value=0.010, format="%.3f", step=0.001)

arquivo = st.file_uploader("Insira o Certificado (PDF)", type=["pdf"])

if arquivo:
    with st.spinner("Injetando contexto e processando via Llama 3.3..."):
        texto = extrair_texto_pdf(arquivo)
        if not texto.strip():
            st.error("Falha: PDF sem texto extraível.")
            st.stop()
            
        # PASSANDO O LIMITE PARA DENTRO DA IA AQUI
        dados_json = estruturar_dados_com_ia(texto[:25000], limite_usuario)
        
        if dados_json and "grandezas" in dados_json:
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da IA")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", sanitizar_texto(resumo.get("instrumento", "N/A")[:30]))
            col_b.metric("Identificação", sanitizar_texto(resumo.get("identificacao", "N/A")[:30]))
            col_c.metric("Laboratório", sanitizar_texto(resumo.get("laboratorio", "N/A")[:30]))
            st.info(f"**Parecer Cognitivo:** {sanitizar_texto(resumo.get('analise_ia', ''))}")
            
            # O Python apenas audita o que a IA devolveu
            df = avaliar_metrologia(dados_json["grandezas"])
            
            if not df.empty:
                tem_reprovado = "REPROVADO" in df['Decisão'].values
                falta_limite = "FALTA LIMITE" in df['Decisão'].values
                
                st.markdown("### 📊 Laudo Metrológico Auditado")
                if tem_reprovado: st.error("🚨 **LAUDO FINAL: REPROVADO**")
                elif falta_limite: st.warning("⚠️ **LAUDO FINAL: PENDENTE**")
                else: st.success("✅ **LAUDO FINAL: APROVADO**")
                
                def cor_status(val):
                    if val == "APROVADO": return 'background-color: rgba(144,238,144,0.2); color:#1e7e34;'
                    elif val == "RESSALVA": return 'background-color: rgba(255,255,102,0.3); color:#856404;'
                    elif val == "REPROVADO": return 'background-color: rgba(255,99,71,0.3); color:#bd2130;'
                    return ''

                st.dataframe(df.style.map(cor_status, subset=['Decisão']), use_container_width=True, hide_index=True)
                
                pdf_bytes = gerar_relatorio_pdf(df, arquivo.name, resumo)
                st.download_button("📥 Baixar Laudo Oficial PDF", data=pdf_bytes, file_name=f"LAUDO_GASCAT_{arquivo.name}", mime="application/pdf", type="primary")
            else:
                st.warning("Tabelas numéricas não encontradas após estruturação.")
