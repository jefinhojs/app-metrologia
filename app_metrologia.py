import streamlit as st
import pdfplumber
import pandas as pd
import json
import datetime
import time
from fpdf import FPDF

# Importações do NOVO SDK do Google e Validador de Dados
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# --- 1. DEFINIÇÃO ABSOLUTA DA ESTRUTURA DE DADOS (POKA-YOKE) ---
# Isso obriga a IA a nunca errar o formato do retorno.
class PontoCalibracao(BaseModel):
    vrm: float = Field(description="Valor de Referência (Padrão ou Ref)")
    vim: float = Field(description="Valor Indicado (Mensurando ou UUT)")
    erro: float = Field(description="Erro de medição (UUT - Ref ou Desvio)")
    incerteza: float = Field(description="Incerteza Expandida")
    limite: float = Field(description="Limite de Erro ou Tolerância. Se não existir, DEVE ser 0.0")

class RelatorioMetrologico(BaseModel):
    instrumento: str = Field(description="Nome do instrumento (ex: Durômetro, Manômetro)")
    laboratorio: str = Field(description="Nome do laboratório (ex: CTM, CEIME, LAFTEC)")
    identificacao: str = Field(description="Número de série, OS ou TAG")
    analise_ia: str = Field(description="Breve explicação de como achou os dados, se converteu unidades ou se o limite estava ausente.")
    pontos: list[PontoCalibracao]

# --- 2. CONFIGURAÇÃO DO SISTEMA ---
st.set_page_config(page_title="Gascat - Qualidade Assegurada", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    # Inicializa o NOVO cliente do Google GenAI
    client = genai.Client(api_key=CHAVE_API_GEMINI)
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.stop()

# --- 3. EXTRAÇÃO DE ALTA FIDELIDADE ---
def extrair_texto_layout(arquivo_pdf):
    """Extrai o texto mantendo o alinhamento das colunas (crucial para CTM)."""
    texto = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            # layout=True mantém o espaçamento físico simulando a tabela
            texto += pagina.extract_text(layout=True) + "\n"
    return texto

def processar_ia_estruturada(texto_bruto):
    """Envia o texto com o Molde (Schema) obrigando a IA a retornar dados perfeitos."""
    
    prompt = """
    Você é o Engenheiro Chefe de Metrologia. Analise o certificado de calibração abaixo e extraia a tabela de resultados.
    
    REGRAS DE OURO (Siga rigorosamente):
    1. LABORATÓRIO CTM: O Valor de Referência (Padrão) costuma vir como 'Ref'. O Valor Indicado (Mensurando) costuma vir como 'UUT' (Unit Under Test).
    2. DURÔMETROS: A unidade é Dureza (ex: HRC, HRB). Foque apenas nos números.
    3. UNIDADES MISTAS: Se o padrão estiver em 'mm' e o erro em 'µm', divida os valores em µm por 1000.
    4. TOLERÂNCIA CEGA: Se o certificado não declarar expressamente o "Limite de Erro" na tabela, defina o campo 'limite' como 0.0.
    
    TEXTO DO CERTIFICADO:
    """ + texto_bruto

    max_tentativas = 3
    for tentativa in range(max_tentativas):
        try:
            # Geração forçando a saída Pydantic (100% à prova de quebra de JSON)
            resposta = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RelatorioMetrologico,
                    temperature=0.0 # Temperatura zero para máxima precisão matemática
                )
            )
            # O texto já sai garantido como JSON perfeitamente estruturado
            return json.loads(resposta.text)
            
        except Exception as e:
            if tentativa < max_tentativas - 1:
                time.sleep(5)
            else:
                st.error(f"Falha terminal de comunicação com o Google AI: {e}")
                return None

# --- 4. MOTOR MATEMÁTICO ---
def avaliar_metrologia(lista_pontos):
    resultados = []
    for ponto in lista_pontos:
        vrm = float(ponto.get('vrm', 0))
        vim = float(ponto.get('vim', 0))
        erro = float(ponto.get('erro', 0))
        incerteza = float(ponto.get('incerteza', 0))
        limite = float(ponto.get('limite', 0))
        
        erro_abs = abs(erro)
        impacto_total = erro_abs + incerteza
        porcentagem = (impacto_total / limite) * 100 if limite != 0 else 0
        
        if limite == 0.0:
            status = "FALTA LIMITE"
        elif impacto_total <= limite:
            status = "APROVADO"
        elif erro_abs <= limite and impacto_total > limite:
            status = "RESSALVA"
        else:
            status = "REPROVADO"
            
        resultados.append({
            "Padrão (Ref)": round(vrm, 5),
            "Indicado (UUT)": round(vim, 5),
            "Erro": round(erro, 5),
            "Incerteza (U)": round(incerteza, 5),
            "Limite (Tol)": limite,
            "Impacto Total": round(impacto_total, 5),
            "% Tol. Consumida": round(porcentagem, 2) if limite != 0 else "N/A",
            "Decisão": status
        })
    return pd.DataFrame(resultados)

# --- 5. GERAÇÃO DE RELATÓRIO PDF ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    try:
        pdf.image("logo.png", x=10, y=8, w=40)
    except: pass
    
    pdf.set_y(15)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "LAUDO METROLÓGICO - AVALIAÇÃO DE CERTIFICADO", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"Documento Base: {nome_original} | Data: {datetime.datetime.now().strftime('%d/%m/%Y')} | Área: Usinagem", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, "Síntese Cognitiva da IA:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 9)
    pdf.multi_cell(0, 5, f"Instrumento: {resumo_ia.get('instrumento', 'N/D')} | TAG/OS: {resumo_ia.get('identificacao', 'N/D')} | Laboratório: {resumo_ia.get('laboratorio', 'N/D')}\nAnálise: {resumo_ia.get('analise_ia', 'Sem observações.')}")
    pdf.ln(5)
    
    pdf.set_font("helvetica", "", 9)
    with pdf.table(borders_layout="ALL", text_align="CENTER") as table:
        linha = table.row()
        for coluna in df_resultados.columns:
            linha.cell(coluna)
        for _, row in df_resultados.iterrows():
            linha = table.row()
            for item in row:
                linha.cell(str(item))
                
    pdf.ln(10)
    
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    if tem_reprovado:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(220, 53, 69)
        pdf.cell(0, 10, "STATUS FINAL: REPROVADO - INSTRUMENTO BLOQUEADO", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "A assinatura eletrônica de liberação foi retida.", align="C")
    elif falta_limite:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 10, "STATUS FINAL: PENDENTE - FALTA LIMITE DE TOLERÂNCIA", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "Insira o limite de erro manualmente no sistema da qualidade.", align="C")
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(40, 167, 69)
        pdf.cell(0, 10, "STATUS FINAL: APROVADO - LIBERADO PARA OPERAÇÃO", align="C", new_x="LMARGIN", new_y="NEXT")
        try:
            pdf.image("assinatura.png", x=110, w=70)
        except: pass
            
    return bytes(pdf.output())

# --- 6. INTERFACE ---
st.title("🔬 Motor Metrológico - Modo de Alta Fidelidade")
st.markdown("Equipado com o novo SDK Google GenAI e saídas estruturadas (Anti-Quebra de JSON).")

arquivo_upload = st.file_uploader("Insira o Certificado (PDF)", type=["pdf"])

if arquivo_upload:
    with st.spinner("Analisando layout e mapeando referências (CTM, CEIME, LAFTEC)..."):
        
        texto_pdf = extrair_texto_layout(arquivo_upload)
        dados = processar_ia_estruturada(texto_pdf)
        
        if dados and "pontos" in dados:
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da Engenharia de Dados")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", dados.get("instrumento", "N/A"))
            col_b.metric("OS/TAG", dados.get("identificacao", "N/A"))
            col_c.metric("Laboratório", dados.get("laboratorio", "N/A"))
            st.info(f"**Parecer Semântico:** {dados.get('analise_ia', '')}")
            
            df = avaliar_metrologia(dados["pontos"])
            
            def cor_status(val):
                if val == "APROVADO": return 'background-color: rgba(144,238,144,0.2); color:#1e7e34; font-weight:bold;'
                elif val == "RESSALVA": return 'background-color: rgba(255,255,102,0.3); color:#856404; font-weight:bold;'
                elif val == "REPROVADO": return 'background-color: rgba(255,99,71,0.3); color:#bd2130; font-weight:bold;'
                elif val == "FALTA LIMITE": return 'background-color: rgba(200,200,200,0.3); color:#444444; font-weight:bold;'
                return ''

            st.dataframe(df.style.map(cor_status, subset=['Decisão']), use_container_width=True)
            st.markdown("---")
            
            nome_exportacao = f"{arquivo_upload.name.rsplit('.', 1)[0]}_ANALISADO.pdf"
            pdf_bytes = gerar_relatorio_pdf(df, arquivo_upload.name, dados)
            
            st.download_button("📥 Exportar Laudo Oficial PDF", pdf_bytes, nome_exportacao, "application/pdf", type="primary")

```
