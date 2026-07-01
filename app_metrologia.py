import os
import tempfile
import json
import time
import datetime
import streamlit as st
import pandas as pd
from fpdf import FPDF

# Importações da Arquitetura RAG (LlamaIndex)
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding

# --- 1. CONFIGURAÇÃO SEGURA DO SISTEMA E LLAMAINDEX ---
st.set_page_config(page_title="Gascat - Inteligência Metrológica RAG", layout="wide")

try:
    CHAVE_API_GEMINI = st.secrets["GEMINI_API_KEY"]
    
    # Configuração global do LlamaIndex para utilizar o motor Gemini (Leitura e Vetorização)
    # Utilizamos o modelo 1.5 Flash pela altíssima velocidade em RAG
    Settings.llm = Gemini(model="models/gemini-1.5-flash", api_key=CHAVE_API_GEMINI)
    Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001", api_key=CHAVE_API_GEMINI)
    
except KeyError:
    st.error("Erro Crítico: A API Key do Gemini não foi encontrada no cofre de segredos.")
    st.info("No Streamlit Cloud, vá em Settings > Secrets e insira: GEMINI_API_KEY = 'sua_chave'")
    st.stop()
except Exception as e:
    st.error(f"Erro na inicialização dos modelos: {e}")
    st.stop()


# --- 2. MOTOR RAG (RETRIEVAL-AUGMENTED GENERATION) ---
def estruturar_dados_com_rag(arquivo_upload):
    """
    Salva o PDF em memória volátil, vetoriza o documento, faz a busca semântica
    pelas tabelas e extrai os dados estruturados imunes a ruídos do layout.
    """
    
    # 2.1. Criação de arquivo temporário (Necessário para leitura do LlamaIndex)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(arquivo_upload.getvalue())
        caminho_temp = tmp_file.name

    try:
        # 2.2. Ingestão e Indexação
        documentos = SimpleDirectoryReader(input_files=[caminho_temp]).load_data()
        index = VectorStoreIndex.from_documents(documentos)
        
        # 2.3. Configuração do Motor de Busca (Query Engine)
        query_engine = index.as_query_engine(
            similarity_top_k=3, # Foca apenas nas 3 seções mais relevantes do PDF
        )
        
        prompt = """
        Você é um Engenheiro Metrologista Sênior atuando na extração de dados.
        Busque no documento os resultados técnicos da calibração (tabelas com pontos medidos, padrões, erros e limites).
        
        REGRAS DE CONVERSÃO E LEITURA:
        1. UNIDADES MISTAS: Se o Valor de Referência estiver em 'mm' e o Desvio/Erro/Incerteza estiver em 'µm', CONVERTA os valores em µm para mm (dividindo por 1000).
        2. BLOCOS PADRÃO/PESOS: Não possuem "Valor Indicado". Possuem "Valor Nominal" (vrm) e "Desvio Central" (erro). Trate "Desvio" como "erro".
        
        FORMATO DE SAÍDA ESTRITO (JSON):
        Retorne APENAS um objeto JSON válido, contendo as chaves "resumo" e "pontos".
        
        Estrutura exata exigida:
        {
          "resumo": {
            "instrumento": "Nome do instrumento",
            "laboratorio": "Nome do laboratório emissor",
            "identificacao": "Número do certificado ou TAG",
            "analise_ia": "Resumo de 2 linhas informando se foi necessário converter unidades e quantos pontos achou."
          },
          "pontos": [
            {"vrm": 1.0, "vim": 1.00007, "erro": 0.00007, "incerteza": 0.00007, "limite": 0.0}
          ]
        }
        
        ATENÇÃO: Se não houver limite de tolerância explícito, preencha "limite" com 0.0.
        NÃO inclua formatação Markdown (```json). Apenas o texto JSON puro.
        """
        
        # 2.4. Execução com Retry (Exponential Backoff) para estabilidade da API
        max_tentativas = 3
        for tentativa in range(max_tentativas):
            try:
                resposta = query_engine.query(prompt)
                
                # Sanitização Implacável do JSON
                texto_limpo = str(resposta).strip()
                if texto_limpo.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2
