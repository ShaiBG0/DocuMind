import { useState, type ChangeEvent } from 'react';
import './index.css';

interface Citation {
  page: number | string;
  content: string;
}

interface Message {
  role: 'user' | 'agent';
  text: string;
  citations?: Citation[];
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const uploadFile = async () => {
    if (!file) return;
    setUploadStatus('Subiendo...');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData,
      });
      if (response.ok) {
        setUploadStatus('Documento listo. Ya puedes preguntar.');
      } else {
        setUploadStatus('Error al subir el documento.');
      }
    } catch (error) {
      console.error(error);
      setUploadStatus('Error de conexión.');
    }
  };

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: userMessage.text }),
      });
      const data = await response.json();
      
      const agentMessage: Message = { 
        role: 'agent', 
        text: data.respuesta,
        citations: data.citaciones
      };
      setMessages((prev) => [...prev, agentMessage]);
    } catch (error) {
      console.error(error); 
      setMessages((prev) => [...prev, { role: 'agent', text: 'Error de conexión con el servidor.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      <div className="main-card">
        
        <div className="sidebar">
          <h2>DocuMind</h2>
          <div>
            <label>Cargar Documento (PDF)</label>
            <input 
              type="file" 
              accept=".pdf" 
              onChange={handleFileChange}
              className="file-input"
            />
            <button 
              onClick={uploadFile}
              className="btn-process"
            >
              Procesar PDF
            </button>
            {uploadStatus && <p className="status">{uploadStatus}</p>}
          </div>
        </div>

        <div className="chat-area">
          <div className="message-list">
            {messages.length === 0 && (
              <div className="empty-state">Sube un documento y comienza a preguntar.</div>
            )}
            
            {messages.map((msg, idx) => (
              <div key={idx} className={`message-wrapper ${msg.role}`}>
                <div className={`message-bubble ${msg.role}`}>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</p>
                  
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations">
                      <p>Fuentes referenciadas:</p>
                      {msg.citations.map((cita, i) => (
                        <div key={i} className="citation-box">
                          <span>Página {cita.page}</span>
                          <i>"{cita.content}"</i>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && <div className="loading">Escribiendo...</div>}
          </div>

          <div className="input-area">
            <input 
              type="text" 
              className="chat-input"
              placeholder="Haz una pregunta sobre el documento..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            />
            <button 
              onClick={sendMessage}
              className="btn-send"
              disabled={loading}
            >
              Enviar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;