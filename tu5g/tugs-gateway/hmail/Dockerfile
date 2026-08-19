FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 go build -o hmail main.go

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/hmail .
ENV HMAIL_PORT=8100
EXPOSE 8100
CMD ["./hmail"]
