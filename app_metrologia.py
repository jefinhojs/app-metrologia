import streamlit as st
import pdfplumber
import pandas as pd
import json
import datetime
import time
from fpdf import FPDF

# Importações do NOVO SDK do Google e Validador de Dados Pydantic
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# --- 1. DEFINIÇÃO ABSOLUTA DA ESTRUTURA DE DADOS (POKA-YOKE) ---
class PontoCalibracao(BaseModel):
    vrm: float = Field(description="Valor de Referência (Padrão, Ref ou Valor Nominal)")
    vim: float = Field(description="Valor Indicado (Mensurando, UUT ou Valor Lido)")
    erro: float = Field(description="Erro de medição (UUT - Ref, Desvio ou Erro)")
    incerteza: float = Field(description="Incerteza Expandida (U)")
    limite: float = Field(description="Limite de Erro ou Tolerância. Se não existir expresso na tabela, DEVE ser 0.0")

class RelatorioMetrologico(BaseModel):
    instrumento: str = Field(description="Nome do instrumento (ex: Durômetro, Manômetro, Bloco Padrão)")
    laboratorio: str = Field(description="Nome do laboratório emissor (ex: CTM, CEIME, LAFTEC)")
    identificacao: str = Field(description="Número de série, OS ou TAG do instrumento")
    analise_ia: str = Field(description="Resumo de como encontrou os dados e se o limite estava ausente.")
    pontos: list[PontoCalibracao]

# --- 2. CONFIGURAÇÃO DO SISTEMA ---
st.set_page_config(page_title="Gascat - Qualidade Assegurada", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=CHAVE_API_GEMINI)
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.stop()

# --- 3. EXTRAÇÃO DE ALTA FIDELIDADE (LAYOUT PRESERVADO) ---
def extrair_texto_layout(arquivo_pdf):
    texto = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            # layout=True mantém o alinhamento das colunas da CTM
            texto += pagina.extract_text(layout=True) + "\n"
    return texto

def processar_ia_estruturada(texto_bruto):
    prompt = """
    Você é o Engenheiro Chefe de Metrologia. Extraia a tabela de resultados do certificado abaixo.
    
    REGRAS DE OURO (Siga rigorosamente):
    1. LABORATÓRIO CTM / DURÔMETROS: O Valor de Referência (Padrão) costuma vir como 'Ref'. O Valor Indicado (Mensurando) costuma vir como 'UUT'. A unidade geralmente é HRC, HRB, etc. Foque apenas nos números exatos medidos.
    2. UNIDADES MISTAS: Se o padrão estiver em 'mm' e o erro em 'µm', divida os valores em µm por 1000.
    3. TOLERÂNCIA CEGA: Se o certificado não declarar expressamente o "Limite de Erro", "Erro Máximo" ou "Tolerância" na mesma tabela dos resultados, defina o campo 'limite' obrigatoriamente como 0.0.
    
    TEXTO DO CERTIFICADO:
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
                    temperature=0.0 # Máxima precisão
                )
            )
            
            # Sanitização extra para garantir que não haja sujeira no JSON retornado
            texto_limpo = resposta.text.strip()
            if texto_limpo.startswith("
