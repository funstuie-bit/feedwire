FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG PUBLIC_SHOWCASE=false
ENV PUBLIC_SHOWCASE=$PUBLIC_SHOWCASE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
ENV PORT=3000
EXPOSE 3000
CMD ["node", "build"]
