import streamlit as st
import pdfplumber
import pandas as pd
import google.generativeai as genai
import json
import datetime
import time
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO SEGURA DO SISTEMA ---
st.set_page_config(page_title="Gascat - Inteligência Metrológica Universal", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=CHAVE_API_GEMINI)
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.info("No Streamlit Cloud, vá em Settings > Secrets e insira: GEMINI_API_KEY = 'sua_chave'")
    st.stop()

# --- 2. EXTRAÇÃO E INTELIGÊNCIA ARTIFICIAL ---
def extrair_texto_pdf(arquivo_pdf):
    """Lê todas as páginas do PDF com altíssima velocidade e baixo consumo de RAM."""
    texto = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto += pagina.extract_text() + "\n"
    return texto

def estruturar_dados_com_ia(texto_bruto):
    """
    Aciona o LLM com mapeamento semântico universal para suportar qualquer instrumento
    (Paquímetros, Micrômetros, Durômetros, Manômetros, Subitos, Relógios, Pinos Padrão, etc).
    """
    modelo = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Você é um Engenheiro Metrologista Sênior operando em MODO DESEMPENHO MÁXIMO.
    Sua missão é ler o texto bruto de um certificado de calibração e extrair a TABELA FINAL DE RESULTADOS.
    
    O certificado pode pertencer a QUALQUER UM destes instrumentos: Micrômetros, Paquímetros, Durômetros, Manômetros, Subitos, Relógios Apalpadores/Comparadores, Pinos Padrão, Termômetros, etc.
    
    REGRAS DE OURO DA EXTRAÇÃO:
    1. IGNORE tabelas de "Condições Ambientais" (temperatura e umidade da sala). Busque apenas os resultados da calibração do instrumento.
    2. MAPEAMENTO SEMÂNTICO UNIVERSAL:
       - "vrm" (Padrão): Valor Nominal, Valor de Referência, Padrão, Dureza do Padrão, Dimensão Nominal, Pressão de Referência.
       - "vim" (Indicado): Valor Indicado, Valor Medido, Média das Leituras, Valor Encontrado. (Se o certificado fornecer apenas o VRM e o Erro/Desvio, calcule: VIM = VRM + Erro).
       - "erro" (Erro): Erro, Erro de Medição, Desvio, Desvio Central, Tendência.
       - "incerteza": Incerteza Expandida, Incerteza, U.
       - "limite": Erro Máximo Permissível, Tolerância, Limite de Erro. SE NÃO EXISTIR NO DOCUMENTO, USE 0.0.
    3. CONVERSÃO DE UNIDADES (CRÍTICO PARA DIMENSIONAL): Se o Padrão (VRM) estiver em milímetros ('mm') e o Erro/Incerteza estiver em micrômetros ('µm'), VOCÊ DEVE CONVERTER µm para mm (dividindo por 1000). Para outras grandezas (Dureza HRC/HLD, Pressão bar/psi/kgf, etc), MANTENHA OS VALORES COMO ESTÃO extraídos do certificado.
    
    FORMATO DE SAÍDA ESTRITO (JSON):
    Retorne APENAS um objeto JSON válido, sem marcações Markdown, sem texto antes ou depois.
    {{
      "resumo": {{
        "instrumento": "Nome exato do instrumento (ex: Durômetro, Subito, Manômetro)",
        "laboratorio": "Nome do laboratório emissor",
        "identificacao": "Número do certificado ou TAG",
        "analise_ia": "Breve resumo técnico do que foi extraído, tipo de grandeza e se houve conversão de unidades."
      }},
      "pontos": [
        {{"vrm": 10.0, "vim": 10.01, "erro": 0.01, "incerteza": 0.005, "limite": 0.0}}
      ]
    }}
    
    TEXTO DO CERTIFICADO:
    {texto_bruto}
    """
    
    max_tentativas = 3
    for tentativa in range(max_tentativas):
        try:
            resposta = modelo.generate_content(prompt)
            texto_bruto_ia = resposta.text
            
            # --- BLINDAGEM DE JSON EXTREMA ---
            inicio = texto_bruto_ia.find('{')
            fim = texto_bruto_ia.rfind('}')
            
            if inicio != -1 and fim != -1:
                texto_limpo = texto_bruto_ia[inicio:fim+1]
                dados = json.loads(texto_limpo)
                
                # Filtro Anti-Alucinação: Evita que a IA devolva o exemplo do prompt
                if len(dados.get("pontos", [])) > 0:
                    primeiro_ponto = dados["pontos"][0]
                    if primeiro_ponto.get("vrm") == 10.0 and primeiro_ponto.get("vim") == 10.01 and primeiro_ponto.get("erro") == 0.01:
                        raise ValueError("O LLM retornou o exemplo literal em vez de processar o PDF.")
                        
                return dados
            else:
                raise ValueError("Nenhum formato JSON estruturado foi detectado na resposta do LLM.")
                
        except Exception as e:
            if tentativa < max_tentativas - 1:
                time.sleep(5) 
            else:
                st.error(f"Erro persistente na extração via IA após múltiplas tentativas. Detalhe: {e}")
                return None

# --- 3. MOTOR METROLÓGICO ---
def avaliar_metrologia(lista_pontos):
    """Aplica as regras de negócio da Gascat: Zona de Segurança e Risco de Falsa Aceitação."""
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
        
        # Regras de Decisão Poka-Yoke
        if limite == 0.0:
            status = "FALTA LIMITE"
        elif impacto_total <= limite:
            status = "APROVADO"
        elif erro_abs <= limite and impacto_total > limite:
            status = "RESSALVA"
        else:
            status = "REPROVADO"
            
        resultados.append({
            "Padrão (V.R.M)": vrm,
            "Indicado (V.I.M)": round(vim, 5),
            "Erro": round(erro, 5),
            "Incerteza (U)": round(incerteza, 5),
            "Limite (Tol)": limite,
            "Impacto Total (|Erro| + U)": round(impacto_total, 5),
            "% Tol. Consumida": round(porcentagem, 2) if limite != 0 else "N/A",
            "Decisão": status
        })
    return pd.DataFrame(resultados)

# --- 4. GERAÇÃO DO LAUDO PDF COM ASSINATURA CONDICIONAL ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    """Renderiza o relatório final injetando logo, dados e bloqueio de assinatura em caso de falha."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Tentativa de injeção do Logotipo
    try:
        pdf.image("logo.png", x=10, y=8, w=40)
    except Exception: 
        pass
    
    # Cabeçalho Institucional
    pdf.set_y(15)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "LAUDO METROLÓGICO - AVALIAÇÃO DE CERTIFICADO", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 5, f"Documento Base: {nome_original} | Data: {data_hoje} | Área: Usinagem Gascat", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Bloco de Resumo da Inteligência Artificial
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, "Síntese da Extração (Inteligência Artificial Universal):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 9)
    texto_resumo = f"Instrumento: {resumo_ia.get('instrumento', 'N/D')} | OS/TAG: {resumo_ia.get('identificacao', 'N/D')} | Laboratório: {resumo_ia.get('laboratorio', 'N/D')}\nAnálise: {resumo_ia.get('analise_ia', 'Sem observações adicionais.')}"
    pdf.multi_cell(0, 5, texto_resumo)
    pdf.ln(5)
    
    # Renderização da Tabela de Medições
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
    
    # Auditoria de Qualidade e Condicional de Assinatura
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    if tem_reprovado:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(220, 53, 69)
        pdf.cell(0, 10, "STATUS FINAL: REPROVADO - INSTRUMENTO BLOQUEADO", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "A assinatura eletrônica de liberação foi bloqueada devido à reprovação metrológica.", align="C")
    
    elif falta_limite:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 10, "STATUS FINAL: PENDENTE - FALTA LIMITE DE TOLERÂNCIA", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "Requer intervenção manual. O laboratório não declarou o limite no certificado.", align="C")
    
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(40, 167, 69)
        pdf.cell(0, 10, "STATUS FINAL: APROVADO - LIBERADO PARA OPERAÇÃO", align="C", new_x="LMARGIN", new_y="NEXT")
        
        # Injeção da Assinatura apenas se aprovado/ressalva
        try:
            pdf.image("assinatura.png", x=110, w=70)
        except Exception:
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("helvetica", "I", 10)
            pdf.cell(0, 10, "(Aviso: O arquivo 'assinatura.png' não foi localizado no diretório do sistema)", align="C")
            
    return bytes(pdf.output())

# --- 5. INTERFACE DO USUÁRIO (STREAMLIT) ---
st.title("🔬 Motor Metrológico Universal Gascat")
st.markdown("Processamento corporativo de calibração via IA para Dimensional, Pressão, Temperatura, Dureza e afins.")

arquivo_upload = st.file_uploader("Insira o Certificado Analítico (PDF)", type=["pdf"])

if arquivo_upload:
    with st.spinner("Analisando tipo de grandeza, mapeando variáveis e estruturando matriz de dados..."):
        texto_extraido = extrair_texto_pdf(arquivo_upload)
        dados_json = estruturar_dados_com_ia(texto_extraido)
        
        if dados_json and "pontos" in dados_json:
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico de Extração (Engenharia Simultânea)")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento Identificado", resumo.get("instrumento", "N/A"))
            col_b.metric("OS/TAG/Série", resumo.get("identificacao", "N/A"))
            col_c.metric("Laboratório Emissor", resumo.get("laboratorio", "N/A"))
            st.info(f"**Parecer Cognitivo da IA:** {resumo.get('analise_ia', 'Sem observações adicionais.')}")
            
            # Processamento Matemático
            df = avaliar_metrologia(dados_json["pontos"])
            
            tem_reprovado = "REPROVADO" in df['Decisão'].values
            tem_ressalva = "RESSALVA" in df['Decisão'].values
            falta_limite = "FALTA LIMITE" in df['Decisão'].values
            
            st.markdown("### 📊 Laudo da Avaliação Metrológica (Tolerância & Falsa Aceitação)")
            if tem_reprovado: 
                st.error("🚨 **LAUDO FINAL: REPROVADO**")
            elif falta_limite:
                st.warning("⚠️ **LAUDO FINAL: PENDENTE (FALTA LIMITE)**")
            elif tem_ressalva: 
                st.warning("⚠️ **LAUDO FINAL: APROVADO COM RESSALVAS**")
            else: 
                st.success("✅ **LAUDO FINAL: APROVADO**")
            
            # Estilização da Matriz
            def cor_status(val):
                if val == "APROVADO": return 'background-color: rgba(144,238,144,0.2); color:#1e7e34; font-weight:bold;'
                elif val == "RESSALVA": return 'background-color: rgba(255,255,102,0.3); color:#856404; font-weight:bold;'
                elif val == "REPROVADO": return 'background-color: rgba(255,99,71,0.3); color:#bd2130; font-weight:bold;'
                elif val == "FALTA LIMITE": return 'background-color: rgba(200,200,200,0.3); color:#444444; font-weight:bold;'
                return ''

            st.dataframe(df.style.map(cor_status, subset=['Decisão']), use_container_width=True)
            
            st.markdown("---")
            
            # Formatação do Arquivo de Saída
            nome_original = arquivo_upload.name
            nome_sem_extensao = nome_original.rsplit(".", 1)[0]
            nome_exportacao = f"{nome_sem_extensao}_ANALISADO.pdf"
            
            # Exportação do PDF
            pdf_bytes = gerar_relatorio_pdf(df, nome_original, resumo)
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.download_button(
                    label="📥 Exportar Laudo Oficial PDF",
                    data=pdf_bytes,
                    file_name=nome_exportacao,
                    mime="application/pdf",
                    type="primary"
                )
