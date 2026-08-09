import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // Selo de build visível na interface. Serve para responder, sem adivinhação, a
  // pergunta "o celular está rodando a versão nova ou o service worker ainda está
  // servindo a antiga?" — que já custou tempo de diagnóstico.
  define: {
    __BUILD_ID__: JSON.stringify(
      new Date().toISOString().slice(0, 16).replace("T", " "),
    ),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Acompanhamento de Finanças",
        short_name: "Finanças",
        description:
          "Acompanhe seus gastos de mercado a partir das notas fiscais.",
        theme_color: "#0f766e",
        background_color: "#0b1120",
        display: "standalone",
        start_url: "/",
        lang: "pt-BR",
        // Ícone único em SVG: escala para qualquer tamanho e evita manter PNGs
        // duplicados no repo. Se algum navegador recusar o SVG no prompt de
        // instalação, exportar 192/512 PNG a partir deste mesmo arquivo.
        icons: [
          {
            src: "/icons/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any",
          },
          {
            src: "/icons/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // Cacheia só o app shell. Respostas da API nunca entram no cache: é dado
        // financeiro pessoal, e um número velho na tela é pior que um spinner.
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        navigateFallbackDenylist: [/^\/api/],
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // Em dev o Vite encaminha /api para o FastAPI, então o código do app usa
      // caminhos relativos igual em produção — sem base URL condicional.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
