# Stage 1: build
FROM node:20-slim AS builder
WORKDIR /app
ARG VITE_API_URL=http://localhost:8001
ARG VITE_WS_URL=ws://localhost:8001/ws
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY . .
RUN npm run build

# Stage 2: serve
FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
