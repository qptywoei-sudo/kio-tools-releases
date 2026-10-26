import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import {fileURLToPath,URL} from 'node:url';
import {resolve} from 'node:path';
import {copyFile} from 'node:fs/promises';
export default defineConfig({base:'/tools/',publicDir:false,plugins:[react(),tailwindcss(),{name:'desktop-index',async writeBundle(options){if(options.dir)await copyFile(resolve(options.dir,'local-tools-standalone.html'),resolve(options.dir,'index.html'));}}],resolve:{alias:{'@':fileURLToPath(new URL('./src',import.meta.url))}},build:{outDir:process.env.GALAXY_TOOLS_UI_OUT_DIR||'dist',emptyOutDir:true,rollupOptions:{input:resolve('local-tools-standalone.html')}}});
