FROM node:18-alpine AS build

WORKDIR /app

# Install ALL dependencies (including devDependencies needed for tsc)
COPY package.json package-lock.json ./
RUN npm install

# Copy source and compile
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# ── Production image ──────────────────────────────────────────────────────────
FROM node:18-alpine

WORKDIR /app

# Install production dependencies only
COPY package.json package-lock.json ./
RUN npm install --omit=dev

# Copy compiled output from the build stage
COPY --from=build /app/dist ./dist

EXPOSE 4000

CMD ["node", "dist/index.js"]
