import os
from typing import TypedDict, Optional, List
from langchain_groq import ChatGroq
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field
from langgraph.graph import START, END, StateGraph

GROQ_API_KEY = os.getenv('GROQ_API_KEY')

llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name='llama-3.3-70b-versatile',
    temperature=0
)

global_retriever = None

class EstadoAgente(TypedDict, total=False):
    pregunta: str
    triaje: dict
    respuesta: str
    citaciones: List[dict]
    rag_exitoso: bool
    accion_final: str

def cargar_documento(ruta_pdf: str):
    global global_retriever
    loader = PyMuPDFLoader(ruta_pdf)
    docs = loader.load()
    
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
    
    embeddings = HuggingFaceEmbeddings(
        model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    )
    
    vectorstore = FAISS.from_documents(chunks, embeddings)
    global_retriever = vectorstore.as_retriever(
        search_type='similarity',
        search_kwargs={'k': 4}
    )
    return len(docs)

PROMPT_TRIAJE = """
Eres un asistente experto en analizar documentos PDF.
Dado el mensaje del usuario, devuelve SOLO un JSON con:
{
    "decision": "AUTO_RESOLVER" | "PEDIR_ACLARACION" | "FUERA_DE_ALCANCE",
    "urgencia": "BAJA" | "MEDIANA" | "ALTA",
    "razon": "explicación breve de la decisión"
}
Reglas:
- AUTO_RESOLVER: preguntas claras sobre el contenido del documento cargado.
- PEDIR_ACLARACION: preguntas vagas o sin contexto suficiente.
- FUERA_DE_ALCANCE: preguntas que no tienen relación con el documento cargado.
"""

class TriajeOut(BaseModel):
    decision: str = Field(description="AUTO_RESOLVER, PEDIR_ACLARACION o FUERA_DE_ALCANCE")
    urgencia: str = Field(description="BAJA, MEDIANA o ALTA")
    razon: str = Field(description="explicación breve de la decisión")

cadena_triaje = llm.with_structured_output(TriajeOut)

def triaje(mensaje: str) -> dict:
    salida: TriajeOut = cadena_triaje.invoke([
        SystemMessage(content=PROMPT_TRIAJE),
        HumanMessage(content=mensaje)
    ])
    return salida.model_dump()

PROMPT_RESPUESTA = PromptTemplate(
    template="""
        Eres un asistente experto en analizar documentos PDF.
        Responde SIEMPRE en español de forma clara, precisa y profesional.
        Basa tu respuesta ÚNICAMENTE en el contexto del documento proporcionado.
        Si la información no está en el contexto, responde exactamente:
        'No encontré información sobre eso en el documento.'
        
        Contexto del documento:
        {contexto}

        Pregunta: {pregunta}

        Respuesta:
    """,
    input_variables=['contexto', 'pregunta']
)

def buscar_en_documento(pregunta: str) -> dict:
    global global_retriever
    if not global_retriever:
        return {
            'respuesta': 'No hay ningún documento cargado en la base de datos.',
            'citaciones': [],
            'encontrado': False
        }

    docs_relevantes = global_retriever.invoke(pregunta)

    if not docs_relevantes:
        return {
            'respuesta': 'No encontré información sobre eso en el documento.',
            'citaciones': [],
            'encontrado': False
        }

    contexto = '\n\n'.join([doc.page_content for doc in docs_relevantes])
    cadena = PROMPT_RESPUESTA | llm | StrOutputParser()
    respuesta = cadena.invoke({'contexto': contexto, 'pregunta': pregunta})

    citaciones_json = [
        {"page": doc.metadata.get('page', 'N/A'), "content": doc.page_content}
        for doc in docs_relevantes
    ]

    if 'No encontré información' in respuesta:
        return {'respuesta': respuesta, 'citaciones': [], 'encontrado': False}

    return {'respuesta': respuesta, 'citaciones': citaciones_json, 'encontrado': True}

def nodo_triaje(state: EstadoAgente) -> EstadoAgente:
    resultado = triaje(state['pregunta'])
    return {'triaje': resultado}

def nodo_auto_resolver(state: EstadoAgente) -> EstadoAgente:
    resultado = buscar_en_documento(state['pregunta'])
    update: EstadoAgente = {
        'respuesta': resultado['respuesta'],
        'citaciones': resultado['citaciones'],
        'rag_exitoso': resultado['encontrado']
    }
    if resultado['encontrado']:
        update['accion_final'] = 'AUTO_RESOLVER'
    return update

def nodo_pedir_aclaracion(state: EstadoAgente) -> EstadoAgente:
    return {
        'respuesta': "Tu pregunta es un poco general. ¿Podrías ser más específico?",
        'citaciones': [],
        'rag_exitoso': False,
        'accion_final': 'PEDIR_ACLARACION'
    }

def nodo_fuera_de_alcance(state: EstadoAgente) -> EstadoAgente:
    return {
        'respuesta': "Esa pregunta está fuera del alcance de este asistente. Solo puedo responder sobre el documento cargado.",
        'citaciones': [],
        'rag_exitoso': False,
        'accion_final': 'FUERA_DE_ALCANCE'
    }

def arista_decision_triaje(state: EstadoAgente) -> str:
    decision = state['triaje']['decision']
    if decision == 'AUTO_RESOLVER': return 'rag'
    elif decision == 'PEDIR_ACLARACION': return 'aclaracion'
    else: return 'alcance'

def arista_decision_rag(state: EstadoAgente) -> str:
    if state.get('rag_exitoso'): return 'ok'
    PALABRAS_ACLARACION = ['más', 'detalle', 'explica', 'amplía', 'qué más']
    if any(p in state['pregunta'].lower() for p in PALABRAS_ACLARACION):
        return 'aclaracion'
    return 'alcance'

workflow = StateGraph(EstadoAgente)
workflow.add_node('triaje', nodo_triaje)
workflow.add_node('auto_resolver', nodo_auto_resolver)
workflow.add_node('pedir_aclaracion', nodo_pedir_aclaracion)
workflow.add_node('fuera_de_alcance', nodo_fuera_de_alcance)

workflow.add_edge(START, 'triaje')
workflow.add_conditional_edges('triaje', arista_decision_triaje, {
    'rag': 'auto_resolver',
    'aclaracion': 'pedir_aclaracion',
    'alcance': 'fuera_de_alcance'
})
workflow.add_conditional_edges('auto_resolver', arista_decision_rag, {
    'ok': END,
    'aclaracion': 'pedir_aclaracion',
    'alcance': 'fuera_de_alcance'
})
workflow.add_edge('pedir_aclaracion', END)
workflow.add_edge('fuera_de_alcance', END)

grafo = workflow.compile()