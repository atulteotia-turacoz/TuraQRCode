import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// ADMIN_BASE_PATH=/admin/ serves the administration app under a path of the customer domain.
const raw=process.env.ADMIN_BASE_PATH||'/';
const base=('/'+raw.replace(/^\/+|\/+$/g,'')+'/').replace('//','/');
export default defineConfig({base,plugins:[react()],server:{proxy:{'/api/':process.env.API_PROXY_TARGET||'http://127.0.0.1:8000'}}});
