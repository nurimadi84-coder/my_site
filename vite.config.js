import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Тот же номер, что проверяет сервер (core/config.py: shop_phone): без валидного PHONE_E164 сборка не идёт.
function shopPhone(env) {
  let digits = String(env.PHONE_E164 || "").replace(/\D/g, "");
  if (digits.length === 10) digits = `7${digits}`;
  if (digits.length === 11 && digits.startsWith("8")) digits = `7${digits.slice(1)}`;
  if (!/^7\d{10}$/.test(digits)) {
    throw new Error(
      `PHONE_E164 в .env ${env.PHONE_E164 ? `некорректен («${env.PHONE_E164}»)` : "не задан"}: нужен номер вида 77071234567`
    );
  }
  return digits;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    define: {
      __SHOP_PHONE__: JSON.stringify(shopPhone(env)),
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      // не /assets/ — там фото товаров и логотип с Python-сервера
      assetsDir: "app",
    },
    server: {
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8780",
        "/assets": "http://127.0.0.1:8780",
      },
    },
  };
});
