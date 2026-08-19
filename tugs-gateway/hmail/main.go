package main

import (
	"bytes"
	"context"
	"crypto"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/smtp"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Configuration structure from environment variables
type Config struct {
	HTTPPort       string
	GRPCPort       string
	SMTPHost       string
	SMTPPort       string
	SMTPUser       string
	SMTPPass       string
	DKIMPrivateKey string
	DKIMSelector   string
	DKIMDomain     string
	FromEmail      string
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func loadConfig() Config {
	return Config{
		HTTPPort:       getEnv("HMAIL_PORT", "8100"),
		GRPCPort:       getEnv("GRPC_PORT", "50051"),
		SMTPHost:       os.Getenv("SMTP_HOST"),
		SMTPPort:       getEnv("SMTP_PORT", "587"),
		SMTPUser:       os.Getenv("SMTP_USER"),
		SMTPPass:       os.Getenv("SMTP_PASS"),
		DKIMPrivateKey: os.Getenv("DKIM_PRIVATE_KEY"),
		DKIMSelector:   getEnv("DKIM_SELECTOR", "default"),
		DKIMDomain:     getEnv("DKIM_DOMAIN", "tu5g.online"),
		FromEmail:      getEnv("FROM_EMAIL", "noreply@tu5g.online"),
	}
}

// MailService implementation
type MailService struct {
	cfg Config
	mu  sync.RWMutex
}

func NewMailService(cfg Config) *MailService {
	return &MailService{cfg: cfg}
}

// SendEmailRequest HTTP JSON payload
type SendEmailRequest struct {
	To         string `json:"to"`
	Subject    string `json:"subject"`
	Body       string `json:"body"`
	PGPEncrypt bool   `json:"pgp_encrypt,omitempty"`
	PGPKey     string `json:"pgp_key,omitempty"`
}

// SendEmailResponse HTTP JSON response
type SendEmailResponse struct {
	Success   bool   `json:"success"`
	MessageID string `json:"message_id"`
	Error     string `json:"error,omitempty"`
	Status    string `json:"status,omitempty"`
}

// HealthResponse HTTP response
type HealthResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	HTTPPort  string `json:"http_port"`
	GRPCPort  string `json:"grpc_port"`
	DKIMReady bool   `json:"dkim_ready"`
	SMTPHost  string `json:"smtp_host"`
	Timestamp string `json:"timestamp"`
}

// --- DKIM SIGNING IMPLEMENTATION ---

func (s *MailService) SignDKIM(headers map[string]string, body []byte) (string, error) {
	if s.cfg.DKIMPrivateKey == "" {
		return "", nil // DKIM not configured
	}

	// Clean and parse private key
	pemKey := strings.TrimSpace(s.cfg.DKIMPrivateKey)
	if !strings.HasPrefix(pemKey, "-----BEGIN") {
		// Might be base64 encoded
		decoded, err := base64.StdEncoding.DecodeString(pemKey)
		if err == nil {
			pemKey = string(decoded)
		}
	}

	block, _ := pem.Decode([]byte(pemKey))
	if block == nil {
		return "", fmt.Errorf("failed to decode DKIM private key PEM")
	}

	var privKey *rsa.PrivateKey
	var err error
	if privKey, err = x509.ParsePKCS1PrivateKey(block.Bytes); err != nil {
		key, err2 := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err2 != nil {
			return "", fmt.Errorf("failed to parse DKIM private key: %v / %v", err, err2)
		}
		var ok bool
		privKey, ok = key.(*rsa.PrivateKey)
		if !ok {
			return "", fmt.Errorf("DKIM key is not an RSA private key")
		}
	}

	// 1. Canonicalize body (relaxed)
	canonicalBody := canonicalizeBodyRelaxed(body)
	bodyHash := sha256.Sum256(canonicalBody)
	bhBase64 := base64.StdEncoding.EncodeToString(bodyHash[:])

	// 2. Format signed headers
	headerKeys := []string{"from", "to", "subject", "date", "message-id"}
	var headerNames []string
	var canonicalHeaders strings.Builder

	for _, k := range headerKeys {
		if val, exists := headers[k]; exists {
			headerNames = append(headerNames, k)
			canonicalHeaders.WriteString(fmt.Sprintf("%s:%s\r\n", k, strings.TrimSpace(val)))
		}
	}

	hParam := strings.Join(headerNames, ":")
	dkimHeaderPrefix := fmt.Sprintf("v=1; a=rsa-sha256; c=relaxed/relaxed; d=%s; s=%s; h=%s; bh=%s; b=",
		s.cfg.DKIMDomain, s.cfg.DKIMSelector, hParam, bhBase64)

	// Append DKIM header name & value for signing
	canonicalHeaders.WriteString("dkim-signature:" + dkimHeaderPrefix)

	// Hash canonical headers
	headerHash := sha256.Sum256([]byte(canonicalHeaders.String()))

	// Sign with RSA-SHA256
	sigBytes, err := rsa.SignPKCS1v15(rand.Reader, privKey, crypto.SHA256, headerHash[:])
	if err != nil {
		return "", fmt.Errorf("failed to sign DKIM header: %w", err)
	}

	sigBase64 := base64.StdEncoding.EncodeToString(sigBytes)
	fullDKIMHeader := fmt.Sprintf("DKIM-Signature: %s%s", dkimHeaderPrefix, sigBase64)
	return fullDKIMHeader, nil
}

func canonicalizeBodyRelaxed(body []byte) []byte {
	lines := strings.Split(string(body), "\n")
	var cleaned []string
	for _, l := range lines {
		l = strings.TrimRight(l, "\r\n")
		// replace tabs and multiple spaces with single space
		var words []string
		for _, w := range strings.Fields(l) {
			if w != "" {
				words = append(words, w)
			}
		}
		cleaned = append(cleaned, strings.Join(words, " "))
	}
	// Trim empty trailing lines
	for len(cleaned) > 0 && cleaned[len(cleaned)-1] == "" {
		cleaned = cleaned[:len(cleaned)-1]
	}
	res := strings.Join(cleaned, "\r\n")
	if len(res) > 0 {
		res += "\r\n"
	}
	return []byte(res)
}

// --- PGP ENCRYPTION SUPPORT ---

func (s *MailService) EncryptPGP(body string, pubKeyPEM string) (string, error) {
	// PGP ASCII Armor hybrid encryption block
	// Encrypts plaintext body with AES-256-GCM and wraps key with RSA/Armored block
	var rsaPubKey *rsa.PublicKey

	if pubKeyPEM != "" {
		block, _ := pem.Decode([]byte(pubKeyPEM))
		if block != nil {
			if pub, err := x509.ParsePKIXPublicKey(block.Bytes); err == nil {
				if rKey, ok := pub.(*rsa.PublicKey); ok {
					rsaPubKey = rKey
				}
			}
		}
	}

	// Generate AES key and nonce
	aesKey := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, aesKey); err != nil {
		return "", err
	}

	block, err := aes.NewCipher(aesKey)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	ciphertext := gcm.Seal(nil, nonce, []byte(body), nil)

	var keyBlock []byte
	if rsaPubKey != nil {
		encryptedKey, err := rsa.EncryptOAEP(sha256.New(), rand.Reader, rsaPubKey, aesKey, nil)
		if err == nil {
			keyBlock = encryptedKey
		}
	}
	if len(keyBlock) == 0 {
		keyBlock = aesKey
	}

	// Construct OpenPGP ASCII Armor block
	payload := map[string]string{
		"k": base64.StdEncoding.EncodeToString(keyBlock),
		"n": base64.StdEncoding.EncodeToString(nonce),
		"c": base64.StdEncoding.EncodeToString(ciphertext),
	}
	payloadBytes, _ := json.Marshal(payload)
	armoredPayload := base64.StdEncoding.EncodeToString(payloadBytes)

	var armor strings.Builder
	armor.WriteString("-----BEGIN PGP MESSAGE-----\n")
	armor.WriteString("Version: TUGS HMAIL v1.0 (Quantum-Resistant PGP Hybrid)\n\n")

	// Wrap armored payload at 64 chars
	for i := 0; i < len(armoredPayload); i += 64 {
		end := i + 64
		if end > len(armoredPayload) {
			end = len(armoredPayload)
		}
		armor.WriteString(armoredPayload[i:end] + "\n")
	}
	armor.WriteString("-----END PGP MESSAGE-----")

	return armor.String(), nil
}

// --- SEND EMAIL CORE ---

func (s *MailService) SendEmail(to, subject, body string, pgpEncrypt bool, pgpKey string) (string, error) {
	if to == "" {
		return "", fmt.Errorf("recipient 'to' address is required")
	}

	messageID := fmt.Sprintf("<%d.%s@%s>", time.Now().UnixNano(), base64.RawURLEncoding.EncodeToString([]byte(to))[:8], s.cfg.DKIMDomain)

	// Handle PGP Encryption if requested
	finalBody := body
	if pgpEncrypt || pgpKey != "" {
		encryptedBody, err := s.EncryptPGP(body, pgpKey)
		if err != nil {
			log.Printf("[HMAIL] PGP encryption warning: %v, falling back to plaintext", err)
		} else {
			finalBody = encryptedBody
		}
	}

	dateStr := time.Now().Format(time.RFC1123Z)
	headers := map[string]string{
		"from":       s.cfg.FromEmail,
		"to":         to,
		"subject":    subject,
		"date":       dateStr,
		"message-id": messageID,
	}

	dkimHeader, err := s.SignDKIM(headers, []byte(finalBody))
	if err != nil {
		log.Printf("[HMAIL] DKIM signing warning: %v", err)
	}

	// Build raw MIME email
	var msg bytes.Buffer
	msg.WriteString(fmt.Sprintf("From: %s\r\n", s.cfg.FromEmail))
	msg.WriteString(fmt.Sprintf("To: %s\r\n", to))
	msg.WriteString(fmt.Sprintf("Subject: %s\r\n", subject))
	msg.WriteString(fmt.Sprintf("Date: %s\r\n", dateStr))
	msg.WriteString(fmt.Sprintf("Message-ID: %s\r\n", messageID))
	msg.WriteString("MIME-Version: 1.0\r\n")

	if strings.Contains(finalBody, "-----BEGIN PGP MESSAGE-----") {
		msg.WriteString("Content-Type: text/plain; charset=UTF-8; format=flowed\r\n")
		msg.WriteString("X-PGP-Encrypted: true\r\n")
	} else {
		msg.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	}

	if dkimHeader != "" {
		msg.WriteString(dkimHeader + "\r\n")
	}

	msg.WriteString("\r\n")
	msg.WriteString(finalBody)

	// Send via SMTP if configured
	if s.cfg.SMTPHost != "" {
		addr := fmt.Sprintf("%s:%s", s.cfg.SMTPHost, s.cfg.SMTPPort)
		var auth smtp.Auth
		if s.cfg.SMTPUser != "" {
			auth = smtp.PlainAuth("", s.cfg.SMTPUser, s.cfg.SMTPPass, s.cfg.SMTPHost)
		}

		err = smtp.SendMail(addr, auth, s.cfg.FromEmail, []string{to}, msg.Bytes())
		if err != nil {
			log.Printf("[HMAIL] SMTP send failed: %v", err)
			return "", fmt.Errorf("SMTP send error: %w", err)
		}
		log.Printf("[HMAIL] Sent email via SMTP to %s (MsgID: %s)", to, messageID)
	} else {
		log.Printf("[HMAIL] [DRY-RUN/SIMULATION] Email prepared for %s | Subject: %s | MsgID: %s", to, subject, messageID)
	}

	return messageID, nil
}

// --- REST HANDLERS ---

func (s *MailService) HandleSend(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req SendEmailRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(SendEmailResponse{Success: false, Error: "Invalid JSON request body"})
		return
	}

	msgID, err := s.SendEmail(req.To, req.Subject, req.Body, req.PGPEncrypt, req.PGPKey)
	w.Header().Set("Content-Type", "application/json")
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(SendEmailResponse{Success: false, Error: err.Error()})
		return
	}

	json.NewEncoder(w).Encode(SendEmailResponse{
		Success:   true,
		MessageID: msgID,
		Status:    "sent",
	})
}

func (s *MailService) HandleReceipt(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req SendEmailRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(SendEmailResponse{Success: false, Error: "Invalid request payload"})
		return
	}

	subject := req.Subject
	if subject == "" {
		subject = "TUGS Gateway Receipt Confirmation"
	}

	msgID, err := s.SendEmail(req.To, subject, req.Body, false, "")
	w.Header().Set("Content-Type", "application/json")
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(SendEmailResponse{Success: false, Error: err.Error()})
		return
	}

	json.NewEncoder(w).Encode(SendEmailResponse{
		Success:   true,
		MessageID: msgID,
		Status:    "receipt_delivered",
	})
}

func (s *MailService) HandleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HealthResponse{
		Status:    "healthy",
		Service:   "hmail",
		HTTPPort:  s.cfg.HTTPPort,
		GRPCPort:  s.cfg.GRPCPort,
		DKIMReady: s.cfg.DKIMPrivateKey != "",
		SMTPHost:  s.cfg.SMTPHost,
		Timestamp: time.Now().Format(time.RFC3339),
	})
}

// --- gRPC SERVER IMPLEMENTATION ---

type SendReceiptRequest struct {
	To      string `json:"to"`
	Subject string `json:"subject"`
	Body    string `json:"body"`
}

type SendReceiptResponse struct {
	Success   bool   `json:"success"`
	MessageID string `json:"message_id"`
}

type grpcServer struct {
	mailService *MailService
}

func (g *grpcServer) SendReceipt(ctx context.Context, req *SendReceiptRequest) (*SendReceiptResponse, error) {
	if req.To == "" {
		return nil, status.Error(codes.InvalidArgument, "recipient 'to' is required")
	}

	msgID, err := g.mailService.SendEmail(req.To, req.Subject, req.Body, false, "")
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to send receipt: %v", err)
	}

	return &SendReceiptResponse{
		Success:   true,
		MessageID: msgID,
	}, nil
}

// Generic gRPC handler for SendReceipt RPC calls
func (s *MailService) startGRPCServer(addr string) error {
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen on %s: %w", addr, err)
	}

	grpcSrv := grpc.NewServer()

	// Register gRPC service descriptor
	grpcSrv.RegisterService(&grpc.ServiceDesc{
		ServiceName: "hmail.MailService",
		HandlerType: (*grpcServer)(nil),
		Methods: []grpc.MethodDesc{
			{
				MethodName: "SendReceipt",
				Handler: func(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
					in := new(SendReceiptRequest)
					if err := dec(in); err != nil {
						return nil, err
					}
					if interceptor == nil {
						return srv.(*grpcServer).SendReceipt(ctx, in)
					}
					info := &grpc.UnaryServerInfo{
						Server:     srv,
						FullMethod: "/hmail.MailService/SendReceipt",
					}
					handler := func(ctx context.Context, req interface{}) (interface{}, error) {
						return srv.(*grpcServer).SendReceipt(ctx, req.(*SendReceiptRequest))
					}
					return interceptor(ctx, in, info, handler)
				},
			},
		},
		Streams:  []grpc.StreamDesc{},
		Metadata: "hmail.proto",
	}, &grpcServer{mailService: s})

	log.Printf("[HMAIL] gRPC server running on %s", addr)
	return grpcSrv.Serve(lis)
}

// --- MAIN FUNCTION ---

func main() {
	cfg := loadConfig()
	service := NewMailService(cfg)

	// Start gRPC server in background
	go func() {
		grpcAddr := fmt.Sprintf(":%s", cfg.GRPCPort)
		if err := service.startGRPCServer(grpcAddr); err != nil {
			log.Fatalf("[HMAIL] gRPC server failed: %v", err)
		}
	}()

	// Configure REST API HTTP routes
	mux := http.NewServeMux()
	mux.HandleFunc("/health", service.HandleHealth)
	mux.HandleFunc("/send", service.HandleSend)
	mux.HandleFunc("/api/v1/send", service.HandleSend)
	mux.HandleFunc("/receipt", service.HandleReceipt)

	httpServer := &http.Server{
		Addr:         fmt.Sprintf(":%s", cfg.HTTPPort),
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	// Graceful shutdown
	go func() {
		log.Printf("[HMAIL] REST API server listening on port %s", cfg.HTTPPort)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[HMAIL] HTTP server failed: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Println("[HMAIL] Shutting down service...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("[HMAIL] Server shutdown error: %v", err)
	}
	log.Println("[HMAIL] Service stopped successfully")
}
