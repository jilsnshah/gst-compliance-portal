# Build the static bundle, then serve it from nginx alongside a proxy to the
# API. One origin for the browser means no CORS and no API URL to configure on
# each office machine.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Empty base URL = same origin, so the browser calls /api on whatever host it
# loaded the page from. Works for every machine on the LAN without a rebuild.
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
