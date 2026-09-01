import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { watchSwUpdate } from './lib/swUpdate.js';
import './index.css';

// 離線版沒有 SW（file:// 註冊不了），這支自己會判斷後直接返回
watchSwUpdate();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
