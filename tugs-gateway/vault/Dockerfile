FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 go build -o vault main.go

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/vault .
ENV VAULT_PORT=8080
EXPOSE 8080
CMD ["./vault"]
