# Particle Lab — 프론트 Dockerfile (Next.js 14 dev 서버)

FROM node:20-slim

WORKDIR /app

# 의존성 캐시
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# 코드
COPY . .

EXPOSE 3001
ENV HOST=0.0.0.0
ENV PORT=3001
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3001"]
