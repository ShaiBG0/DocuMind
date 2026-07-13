import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import cargar_documento, grafo

app = FastAPI(title="Agente RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp_docs", exist_ok=True)

class ChatRequest(BaseModel):
    pregunta: str

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")
    
    file_path = f"temp_docs/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        pages_loaded = cargar_documento(file_path)
        return {"message": "Documento procesado y vectorizado correctamente", "paginas": pages_loaded}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        resultado = grafo.invoke({'pregunta': request.pregunta})
        return {
            "respuesta": resultado.get('respuesta'),
            "citaciones": resultado.get('citaciones', []),
            "decision_triaje": resultado.get('triaje', {}).get('decision')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))