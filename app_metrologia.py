import streamlit as st
import pdfplumber
import pandas as pd
import json
import datetime
import time
import io
from fpdf import FPDF
from typing import List  # <--- BIBLIOTECA UNIVERSAL DE TIPAGEM

# Importações do SDK do Google e Validador de Dados Pydantic
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# --- 1. DEFINIÇÃO DA ESTRUTURA DE DADOS ---
class PontoCalibracao(BaseModel):
    vrm: float = Field(description="Valor de Referência (Padrão, Ref ou Valor Nominal)")
    vim: float = Field(description="Valor Indicado (Mensurando, UUT ou Valor Lido)")
    erro: float = Field(description="Erro de medição (UUT - Ref, Desvio ou Erro)")
    incerteza: float = Field(description="Incerteza Expandida (U)")
    limite: float = Field(description="Limite de Erro ou Tolerância. Se não existir expresso na tabela, DEVE ser 0.0")

class RelatorioMetrologico(BaseModel):
    instrumento: str = Field(description="Nome do instrumento")
    laboratorio: str = Field(description="Nome do laboratório emissor")
    identificacao: str = Field(description="Número de série, OS ou TAG")
    analise_ia: str = Field(description="Resumo da análise")
    pontos: List[PontoCalibracao]  # <--- CORREÇÃO AQUI: 'List' COM L MAIÚSCULO

# --- 2. CONFIGURAÇÃO ---
st.set_page_config(page_title="Gascat - Qualidade Assegurada", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=CHAVE_API_GEMINI)
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.stop()

# --- 3. EXTRAÇÃO ---
def extrair_texto_layout(arquivo_pdf):
    texto = ""
    # Uso do io.BytesIO garante que o pdfplumber leia o arquivo em memória na nuvem sem falhas
    with pdfplumber.open(io.BytesIO(arquivo_pdf.getvalue())) as pdf:
        for pagina in pdf.pages:
            texto += pagina.extract_text(layout=True) + "\n"
    return texto

def processar_ia_estruturada(texto_bruto):
    prompt = """
    Extraia a tabela de resultados do certificado abaixo.
    1. LABORATÓRIO CTM / DURÔMETROS: 'Ref' = Valor de Referência. 'UUT' = Valor Indicado. Foque nos números.
    2. UNIDADES MISTAS: Se padrão em 'mm' e erro em 'µm', divida µm por 1000.
    3. TOLERÂNCIA CEGA: Se não declarar Limite de Erro, defina 'limite' como 0.0.
    TEXTO:
    """ + texto_bruto

    max_tentativas = 3
    for tentativa in range(max_tentativas):
        try:
            resposta = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RelatorioMetrologico,
                    temperature=0.0
                )
            )
            
            texto_limpo = resposta.text.strip()
            if texto_limpo.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2

### OTIMIZAÇÃO

Com a substituição para `List` da biblioteca `typing`, o código está agnóstico em relação à versão do Python no servidor. Pode colar, salvar no GitHub e acompanhar a inicialização limpa no Streamlit.
