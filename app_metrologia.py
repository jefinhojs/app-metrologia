import streamlit as st
import pdfplumber
import pandas as pd
import google.generativeai as genai
import json
import datetime
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO SEGURA DO SISTEMA ---
st.set_page_config(page_title="Gascat - Inteligência Metrológica", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=CHAVE_API_GEMINI)
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.info("Verifique se o arquivo .streamlit/secrets.toml existe e contém a variável GEMINI_API_KEY.")
    st.stop()

# --- 2. EXTRAÇÃO E INTELIGÊNCIA ARTIFICIAL ---
def extrair_texto_pdf(arquivo_pdf):
    """Lê todas as páginas do PDF para garantir que o contexto completo seja enviado ao LLM."""
    texto = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto += pagina.extract_text() + "\n"
    return texto

def estruturar_dados_com_ia(texto_bruto):
    """
    Aciona o LLM exigindo primeiro um raciocínio interpretativo (resumo) 
    e depois a extração matemática rigorosa (pontos).
    """
    modelo = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    prompt = f"""
    Você é um Engenheiro Metrologista Sênior operando em MODO DESEMPENHO MÁXIMO.
    Sua missão é analisar o texto bruto de um certificado de calibração na íntegra, identificar o contexto e extrair os dados numéricos de calibração com precisão absoluta.
    
    REGRAS OPERACIONAIS (OBRIGATÓRIO):
    1. Leia TODO o documento. Não pare na primeira tabela. Procure por todos os pontos de medição avaliados.
    2. UNIDADES MISTAS: Se o Padrão estiver em 'mm' e o Desvio/Erro/Incerteza estiver em 'µm' (micrômetros), VOCÊ DEVE CONVERTER os valores em µm para mm (dividindo por 1000) ANTES de preencher os dados.
    3. BLOCOS PADRÃO/PESOS: Eles não possuem "Valor Indicado". Possuem "Valor Nominal" (vrm) e "Desvio Central" (erro). Trate o Desvio como Erro e, se necessário, calcule vim = vrm + erro.
    
    FORMATO DE SAÍDA ESTRITO (JSON):
    Retorne APENAS um objeto JSON válido, contendo duas chaves principais: "resumo" e "pontos".
    
    A estrutura deve ser exatamente esta:
    {{
      "resumo": {{
        "instrumento": "Nome do instrumento (ex: Bloco Padrão, Paquímetro)",
        "laboratorio": "Nome do laboratório emissor",
        "identificacao": "Número do certificado, TAG ou OS",
        "analise_ia": "Faça um resumo analítico de 2 a 3 linhas relatando o que encontrou, se houve necessidade de converter unidades (µm para mm), quantos pontos foram lidos e se o laboratório forneceu o limite de tolerância."
      }},
      "pontos": [
        {{
          "vrm": 1.0, 
          "vim": 1.00007, 
          "erro": 0.00007, 
          "incerteza": 0.00007, 
          "limite": 0.0
        }}
      ]
    }}
    
    Se a tolerância (limite) não estiver explícita no certificado, use 0.0.
    NÃO ENVIE formatação Markdown. NÃO ENVIE texto antes ou depois das chaves {{ }}. Apenas o JSON puro.
    
    TEXTO DO CERTIFICADO:
    {texto_bruto}
    """
    
    resposta = modelo.generate_content(prompt)
    
    # Sanitização implacável do retorno para evitar quebra do json.loads
    texto_limpo = resposta.text.strip()
    if texto_limpo.startswith("```json"):
        texto_limpo = texto_limpo[7:]
    if texto_limpo.startswith("```"):
        texto_limpo = texto_limpo[3:]
    if texto_limpo.endswith("```"):
        texto_limpo = texto_limpo[:-3]
    texto_limpo = texto_limpo.strip()
    
    try:
        dados_json = json.loads(texto_limpo)
        return dados_json
    except Exception as e:
        st.error("Falha de conversão: A Inteligência Artificial retornou um formato corrompido.")
        st.code(texto_limpo, language="json")
        return None

# --- 3. MOTOR METROLÓGICO ---
def avaliar_metrologia(lista_pontos):
    """Processa a matemática metrológica com blindagem contra divisões por zero e ausência de limites."""
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

# --- 4. GERAÇÃO DO LAUDO PDF COM ASSINATURA E LOGO ---
def gerar_relatorio_pdf(df_resultados, nome_original, resumo_ia):
    """Constrói o PDF injetando o laudo, logotipo, resumo analítico e assinatura condicionada."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Injeção do Logotipo (Canto Superior Esquerdo)
    try:
        pdf.image("logo.png", x=10, y=8, w=40)
    except FileNotFoundError:
        pass 
    
    # Cabeçalho Institucional
    pdf.set_y(15)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "LAUDO METROLÓGICO - AVALIAÇÃO DE CERTIFICADO DE CALIBRAÇÃO", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 10)
    data_hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 5, f"Documento Base: {nome_original} | Data: {data_hoje} | Área: Usinagem Gascat", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Bloco de Resumo da Inteligência Artificial no PDF
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, "Síntese da Extração (Inteligência Artificial):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 9)
    texto_resumo = f"Instrumento: {resumo_ia.get('instrumento', 'N/D')} | OS/TAG: {resumo_ia.get('identificacao', 'N/D')} | Laboratório: {resumo_ia.get('laboratorio', 'N/D')}\nAnálise: {resumo_ia.get('analise_ia', 'Sem análise fornecida.')}"
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
    
    # Auditoria de Qualidade e Bloqueio de Assinatura
    tem_reprovado = "REPROVADO" in df_resultados['Decisão'].values
    falta_limite = "FALTA LIMITE" in df_resultados['Decisão'].values
    
    if tem_reprovado:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(220, 53, 69) # Vermelho
        pdf.cell(0, 10, "STATUS FINAL: REPROVADO - INSTRUMENTO BLOQUEADO", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "A assinatura eletrônica de liberação foi bloqueada devido à reprovação metrológica.", align="C")
    
    elif falta_limite:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(255, 140, 0) # Laranja
        pdf.cell(0, 10, "STATUS FINAL: PENDENTE - FALTA LIMITE DE TOLERÂNCIA", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 10, "Requer intervenção manual. O laboratório não declarou o limite no certificado.", align="C")
    
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(40, 167, 69) # Verde
        pdf.cell(0, 10, "STATUS FINAL: APROVADO - LIBERADO PARA OPERAÇÃO", align="C", new_x="LMARGIN", new_y="NEXT")
        
        # Injeção da Assinatura (Apenas se aprovado/ressalva)
        try:
            pdf.image("assinatura.png", x=110, w=70)
        except FileNotFoundError:
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("helvetica", "I", 10)
            pdf.cell(0, 10, "(Aviso: O arquivo 'assinatura.png' não foi localizado no diretório do sistema)", align="C")
            
    return bytes(pdf.output())

# --- 5. INTERFACE DO USUÁRIO (STREAMLIT) ---
st.title("🔬 Motor Metrológico Universal - Nível Sênior")
st.markdown("Processamento avançado de certificados via Inteligência Artificial com emissão automática de laudos rastreáveis.")

arquivo = st.file_uploader("Insira o Certificado Analítico (PDF)", type=["pdf"])

if arquivo:
    with st.spinner("Analisando todas as páginas do documento e estruturando interpretação cognitiva..."):
        texto = extrair_texto_pdf(arquivo)
        dados_json = estruturar_dados_com_ia(texto)
        
        if dados_json and "pontos" in dados_json:
            # Renderização do Resumo da IA
            resumo = dados_json.get("resumo", {})
            st.markdown("---")
            st.markdown("### 🧠 Diagnóstico da Inteligência Artificial")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Instrumento", resumo.get("instrumento", "N/A"))
            col_b.metric("OS/TAG", resumo.get("identificacao", "N/A"))
            col_c.metric("Laboratório", resumo.get("laboratorio", "N/A"))
            st.info(f"**Parecer da Leitura:** {resumo.get('analise_ia', 'Sem observações adicionais.')}")
            
            # Processamento Matemático
            df = avaliar_metrologia(dados_json["pontos"])
            
            tem_reprovado = "REPROVADO" in df['Decisão'].values
            tem_ressalva = "RESSALVA" in df['Decisão'].values
            falta_limite = "FALTA LIMITE" in df['Decisão'].values
            
            st.markdown("### 📊 Laudo da Avaliação Metrológica")
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

            st.dataframe(
                df.style.map(cor_status, subset=['Decisão']), 
                use_container_width=True
            )
            
            st.markdown("---")
            
            # Formatação do Arquivo de Saída
            nome_original = arquivo.name
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
