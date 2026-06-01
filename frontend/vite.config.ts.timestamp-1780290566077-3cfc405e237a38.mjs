// vite.config.ts
import { defineConfig } from "file:///D:/Admission-Pilot/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///D:/Admission-Pilot/frontend/node_modules/@vitejs/plugin-react/dist/index.mjs";
import { crx } from "file:///D:/Admission-Pilot/frontend/node_modules/@crxjs/vite-plugin/dist/index.mjs";

// manifest.json
var manifest_default = {
  manifest_version: 3,
  name: "Admission-Pilot AI Helper",
  version: "1.0.0",
  description: "\uB300\uB3D9\uB300\uD559\uAD50 \uC785\uC2DC\uCC98 AI \uC5C5\uBB34 \uD5EC\uD37C \uBC0F \uCE74\uD0C8\uB85C\uADF8 \uAD00\uB9AC\uC790",
  action: {
    default_title: "AI \uD5EC\uD37C \uC5F4\uAE30"
  },
  side_panel: {
    default_path: "index.html"
  },
  permissions: [
    "sidePanel",
    "activeTab",
    "scripting",
    "storage"
  ],
  host_permissions: [
    "http://127.0.0.1:8000/*",
    "http://localhost:8000/*"
  ],
  background: {
    service_worker: "src/background.ts",
    type: "module"
  }
};

// vite.config.ts
import path from "path";
var __vite_injected_original_dirname = "D:\\Admission-Pilot\\frontend";
var vite_config_default = defineConfig({
  plugins: [
    react(),
    crx({ manifest: manifest_default })
  ],
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "./src")
    }
  },
  server: {
    port: 5175,
    strictPort: true,
    // 👇 Vite 5.x로 내려왔기 때문에 이 표준 설정들이 드디어 정상 작동합니다!
    cors: true,
    origin: "http://localhost:5175"
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiLCAibWFuaWZlc3QuanNvbiJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiY29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2Rpcm5hbWUgPSBcIkQ6XFxcXEFkbWlzc2lvbi1QaWxvdFxcXFxmcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiRDpcXFxcQWRtaXNzaW9uLVBpbG90XFxcXGZyb250ZW5kXFxcXHZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9EOi9BZG1pc3Npb24tUGlsb3QvZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJ1xuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuaW1wb3J0IHsgY3J4IH0gZnJvbSAnQGNyeGpzL3ZpdGUtcGx1Z2luJ1xuaW1wb3J0IG1hbmlmZXN0IGZyb20gJy4vbWFuaWZlc3QuanNvbidcbmltcG9ydCBwYXRoIGZyb20gJ3BhdGgnXG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtcbiAgICByZWFjdCgpLFxuICAgIGNyeCh7IG1hbmlmZXN0IH0pLCBcbiAgXSxcbiAgcmVzb2x2ZToge1xuICAgIGFsaWFzOiB7XG4gICAgICAnQCc6IHBhdGgucmVzb2x2ZShfX2Rpcm5hbWUsICcuL3NyYycpLFxuICAgIH0sXG4gIH0sXG4gIHNlcnZlcjoge1xuICAgIHBvcnQ6IDUxNzUsXG4gICAgc3RyaWN0UG9ydDogdHJ1ZSxcbiAgICAvLyBcdUQ4M0RcdURDNDcgVml0ZSA1LnhcdUI4NUMgXHVCMEI0XHVCODI0XHVDNjU0XHVBRTMwIFx1QjU0Q1x1QkIzOFx1QzVEMCBcdUM3NzQgXHVENDVDXHVDOTAwIFx1QzEyNFx1QzgxNVx1QjRFNFx1Qzc3NCBcdUI0RENcdUI1MTRcdUM1QjQgXHVDODE1XHVDMEMxIFx1Qzc5MVx1QjNEOVx1RDU2OVx1QjJDOFx1QjJFNCFcbiAgICBjb3JzOiB0cnVlLFxuICAgIG9yaWdpbjogJ2h0dHA6Ly9sb2NhbGhvc3Q6NTE3NScsXG4gIH0sXG59KSIsICJ7XHJcbiAgXCJtYW5pZmVzdF92ZXJzaW9uXCI6IDMsXHJcbiAgXCJuYW1lXCI6IFwiQWRtaXNzaW9uLVBpbG90IEFJIEhlbHBlclwiLFxyXG4gIFwidmVyc2lvblwiOiBcIjEuMC4wXCIsXHJcbiAgXCJkZXNjcmlwdGlvblwiOiBcIlx1QjMwMFx1QjNEOVx1QjMwMFx1RDU1OVx1QUQ1MCBcdUM3ODVcdUMyRENcdUNDOTggQUkgXHVDNUM1XHVCQjM0IFx1RDVFQ1x1RDM3QyBcdUJDMEYgXHVDRTc0XHVEMEM4XHVCODVDXHVBREY4IFx1QUQwMFx1QjlBQ1x1Qzc5MFwiLFxyXG4gIFwiYWN0aW9uXCI6IHtcclxuICAgIFwiZGVmYXVsdF90aXRsZVwiOiBcIkFJIFx1RDVFQ1x1RDM3QyBcdUM1RjRcdUFFMzBcIlxyXG4gIH0sXHJcbiAgXCJzaWRlX3BhbmVsXCI6IHtcclxuICAgIFwiZGVmYXVsdF9wYXRoXCI6IFwiaW5kZXguaHRtbFwiXHJcbiAgfSxcclxuICBcInBlcm1pc3Npb25zXCI6IFtcclxuICAgIFwic2lkZVBhbmVsXCIsXHJcbiAgICBcImFjdGl2ZVRhYlwiLFxyXG4gICAgXCJzY3JpcHRpbmdcIixcclxuICAgIFwic3RvcmFnZVwiXHJcbiAgXSxcclxuICBcImhvc3RfcGVybWlzc2lvbnNcIjogW1xyXG4gICAgXCJodHRwOi8vMTI3LjAuMC4xOjgwMDAvKlwiLFxyXG4gICAgXCJodHRwOi8vbG9jYWxob3N0OjgwMDAvKlwiXHJcbiAgXSxcclxuICBcImJhY2tncm91bmRcIjoge1xyXG4gICAgXCJzZXJ2aWNlX3dvcmtlclwiOiBcInNyYy9iYWNrZ3JvdW5kLnRzXCIsXHJcbiAgICBcInR5cGVcIjogXCJtb2R1bGVcIlxyXG4gIH1cclxufSJdLAogICJtYXBwaW5ncyI6ICI7QUFBeVEsU0FBUyxvQkFBb0I7QUFDdFMsT0FBTyxXQUFXO0FBQ2xCLFNBQVMsV0FBVzs7O0FDRnBCO0FBQUEsRUFDRSxrQkFBb0I7QUFBQSxFQUNwQixNQUFRO0FBQUEsRUFDUixTQUFXO0FBQUEsRUFDWCxhQUFlO0FBQUEsRUFDZixRQUFVO0FBQUEsSUFDUixlQUFpQjtBQUFBLEVBQ25CO0FBQUEsRUFDQSxZQUFjO0FBQUEsSUFDWixjQUFnQjtBQUFBLEVBQ2xCO0FBQUEsRUFDQSxhQUFlO0FBQUEsSUFDYjtBQUFBLElBQ0E7QUFBQSxJQUNBO0FBQUEsSUFDQTtBQUFBLEVBQ0Y7QUFBQSxFQUNBLGtCQUFvQjtBQUFBLElBQ2xCO0FBQUEsSUFDQTtBQUFBLEVBQ0Y7QUFBQSxFQUNBLFlBQWM7QUFBQSxJQUNaLGdCQUFrQjtBQUFBLElBQ2xCLE1BQVE7QUFBQSxFQUNWO0FBQ0Y7OztBRHJCQSxPQUFPLFVBQVU7QUFKakIsSUFBTSxtQ0FBbUM7QUFNekMsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUztBQUFBLElBQ1AsTUFBTTtBQUFBLElBQ04sSUFBSSxFQUFFLDJCQUFTLENBQUM7QUFBQSxFQUNsQjtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTztBQUFBLE1BQ0wsS0FBSyxLQUFLLFFBQVEsa0NBQVcsT0FBTztBQUFBLElBQ3RDO0FBQUEsRUFDRjtBQUFBLEVBQ0EsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sWUFBWTtBQUFBO0FBQUEsSUFFWixNQUFNO0FBQUEsSUFDTixRQUFRO0FBQUEsRUFDVjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
