FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/40-slipcast-config.sh /docker-entrypoint.d/40-slipcast-config.sh
RUN chmod +x /docker-entrypoint.d/40-slipcast-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
# Point the app at your API at runtime (Cloud Run, Render, Docker Compose)
ENV API_URL=http://localhost:8000
EXPOSE 8080
