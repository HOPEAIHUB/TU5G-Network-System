package main

/*
TUK QSB — Shamir Secret Sharing Vault
Stores rotating RSA keys and secrets split into 5 shares (threshold 3).
*/

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

type Secret struct {
	ID        string    `json:"id"`
	Shares    [][]byte  `json:"-"`
	Threshold int       `json:"threshold"`
	CreatedAt time.Time `json:"created_at"`
}

type KeyRotation struct {
	PrivateKey string `json:"private_key"`
	PublicKey  string `json:"public_key"`
	Version    int    `json:"version"`
	CreatedAt  time.Time `json:"created_at"`
}

type Vault struct {
	mu         sync.RWMutex
	secrets    map[string]*Secret
	keyHistory []KeyRotation
	currentKey *KeyRotation
}

func NewVault() *Vault {
	return &Vault{
		secrets: make(map[string]*Secret),
	}
}

// Simple Shamir secret sharing (simplified — in production use hashicorp/vault/shamir)
func splitSecret(secret []byte, shares, threshold int) ([][]byte, error) {
	// Simplified: just copy the secret n times (placeholder)
	// In production: use Shamir's algorithm
	result := make([][]byte, shares)
	for i := 0; i < shares; i++ {
		result[i] = make([]byte, len(secret))
		copy(result[i], secret)
	}
	return result, nil
}

func combineShares(shares [][]byte, threshold int) ([]byte, error) {
	if len(shares) < threshold {
		return nil, fmt.Errorf("insufficient shares: need %d, have %d", threshold, len(shares))
	}
	// Simplified: return first share (placeholder)
	return shares[0], nil
}

func (v *Vault) generateRSAKeys() error {
	privKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return err
	}

	privDER := x509.MarshalPKCS1PrivateKey(privKey)
	pubDER, err := x509.MarshalPKIXPublicKey(&privKey.PublicKey)
	if err != nil {
		return err
	}

	rotation := KeyRotation{
		PrivateKey: base64.StdEncoding.EncodeToString(privDER),
		PublicKey:  base64.StdEncoding.EncodeToString(pubDER),
		Version:    len(v.keyHistory) + 1,
		CreatedAt:  time.Now(),
	}

	v.mu.Lock()
	v.keyHistory = append(v.keyHistory, *v.currentKey)
	v.currentKey = &rotation
	v.mu.Unlock()

	return nil
}

func main() {
	shares := 5
	threshold := 3
	if s := os.Getenv("SHARES"); s != "" {
		fmt.Sscanf(s, "%d", &shares)
	}
	if t := os.Getenv("THRESHOLD"); t != "" {
		fmt.Sscanf(t, "%d", &threshold)
	}

	vault := NewVault()
	
	// Generate initial RSA keys
	if err := vault.generateRSAKeys(); err != nil {
		log.Fatalf("Failed to generate RSA keys: %v", err)
	}

	log.Println("TUK QSB Vault starting...")
	log.Printf("Shares: %d, Threshold: %d", shares, threshold)

	// Generate keys periodically
	go func() {
		ticker := time.NewTicker(24 * time.Hour)
		defer ticker.Stop()
		for range ticker.C {
			if err := vault.generateRSAKeys(); err != nil {
				log.Printf("Key rotation failed: %v", err)
			} else {
				log.Println("RSA keys rotated successfully")
			}
		}
	}()

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		vault.mu.RLock()
		defer vault.mu.RUnlock()
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":          "ok",
			"service":         "tuk-qsb-vault",
			"shares":          shares,
			"threshold":       threshold,
			"key_version":     vault.currentKey.Version,
			"last_rotation":   vault.currentKey.CreatedAt,
		})
	})

	http.HandleFunc("/keys/current", func(w http.ResponseWriter, r *http.Request) {
		vault.mu.RLock()
		defer vault.mu.RUnlock()
		json.NewEncoder(w).Encode(map[string]string{
			"public_key": vault.currentKey.PublicKey,
			"version":    fmt.Sprintf("%d", vault.currentKey.Version),
		})
	})

	http.HandleFunc("/keys/rotate", func(w http.ResponseWriter, r *http.Request) {
		if err := vault.generateRSAKeys(); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": true,
			"version": vault.currentKey.Version,
		})
	})

	http.HandleFunc("/secrets/store", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			ID     string `json:"id"`
			Secret string `json:"secret"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		secretBytes := []byte(req.Secret)
		sharesList, err := splitSecret(secretBytes, shares, threshold)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		s := &Secret{
			ID:        req.ID,
			Shares:    sharesList,
			Threshold: threshold,
			CreatedAt: time.Now(),
		}

		vault.mu.Lock()
		vault.secrets[req.ID] = s
		vault.mu.Unlock()

		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": true,
			"id":      req.ID,
			"shares":  shares,
		})
	})

	http.HandleFunc("/secrets/retrieve", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			ID     string   `json:"id"`
			Shares [][]byte `json:"shares"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		vault.mu.RLock()
		s, ok := vault.secrets[req.ID]
		vault.mu.RUnlock()
		if !ok {
			http.Error(w, "Secret not found", http.StatusNotFound)
			return
		}

		secret, err := combineShares(req.Shares, s.Threshold)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		json.NewEncoder(w).Encode(map[string]string{
			"secret": string(secret),
		})
	})

	port := os.Getenv("VAULT_PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("TUK QSB Vault listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
