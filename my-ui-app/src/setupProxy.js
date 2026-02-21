const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  // Backend API – strip /api prefix, forward to backend on port 8000
  app.use(
    "/api",
    createProxyMiddleware({
      target: "http://localhost:8000",
      changeOrigin: true,
      pathRewrite: { "^/api": "" },
    }),
  );

  // AI service – strip /ai prefix, forward to ai-service on port 8001
  app.use(
    "/ai",
    createProxyMiddleware({
      target: "http://localhost:8001",
      changeOrigin: true,
      pathRewrite: { "^/ai": "" },
    }),
  );
};
