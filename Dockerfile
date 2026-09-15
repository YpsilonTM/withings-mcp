# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build
RUN npm prune --omit=dev

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV WITHINGS_TOKEN_FILE=/data/tokens.json
RUN addgroup -S withings && adduser -S withings -G withings \
  && mkdir -p /data \
  && chown withings:withings /data
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
USER withings
ENTRYPOINT ["node", "dist/index.js"]
CMD []
