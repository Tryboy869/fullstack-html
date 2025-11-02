"""
============================================
WEBHOOK COMMUNICATION LAYER
============================================
Essence pure du webhook pour communication
frontend ↔ backend temps réel
"""

import hmac
import hashlib
import json
import time
import random
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# ============================================
# CONFIGURATION
# ============================================
SECRET_KEY = "shopnexus-secret-key-2024"
MAX_RETRIES = 3
BASE_BACKOFF = 1  # seconds
MAX_BACKOFF = 60  # seconds
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 30  # seconds

# ============================================
# ENUMS
# ============================================
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, block requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class DeliveryStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CIRCUIT_OPEN = "circuit_open"

# ============================================
# DATA CLASSES
# ============================================
@dataclass
class WebhookEvent:
    """Représente un événement webhook"""
    event_type: str
    payload: Dict[str, Any]
    timestamp: float
    signature: Optional[str] = None
    attempt: int = 0
    
    def to_dict(self):
        return {
            "event": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "attempt": self.attempt
        }

@dataclass
class CircuitBreakerState:
    """État du circuit breaker"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

# ============================================
# CORE: SIGNATURE (HMAC-SHA256)
# ============================================
class SignatureManager:
    """Gestion des signatures HMAC pour sécuriser les webhooks"""
    
    @staticmethod
    def sign(data: Dict[str, Any], secret: str = SECRET_KEY) -> str:
        """
        Génère une signature HMAC-SHA256
        
        Args:
            data: Données à signer
            secret: Clé secrète partagée
            
        Returns:
            Signature hexadécimale
        """
        payload = json.dumps(data, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    @staticmethod
    def verify(data: Dict[str, Any], signature: str, secret: str = SECRET_KEY) -> bool:
        """
        Vérifie une signature HMAC
        
        Args:
            data: Données reçues
            signature: Signature à vérifier
            secret: Clé secrète partagée
            
        Returns:
            True si la signature est valide
        """
        expected_signature = SignatureManager.sign(data, secret)
        return hmac.compare_digest(expected_signature, signature)

# ============================================
# CORE: RETRY LOGIC (EXPONENTIAL BACKOFF)
# ============================================
class RetryHandler:
    """Gestion des retries avec exponential backoff"""
    
    @staticmethod
    def calculate_backoff(attempt: int, base: float = BASE_BACKOFF, max_delay: float = MAX_BACKOFF) -> float:
        """
        Calcule le délai avant le prochain retry
        
        Args:
            attempt: Numéro de la tentative (0-indexed)
            base: Délai de base en secondes
            max_delay: Délai maximum
            
        Returns:
            Délai en secondes avec jitter
        """
        # Exponential: base * 2^attempt
        delay = min(base * (2 ** attempt), max_delay)
        
        # Add jitter (±10% random)
        jitter = delay * 0.1 * (2 * random.random() - 1)
        
        return delay + jitter
    
    @staticmethod
    def should_retry(attempt: int, max_retries: int = MAX_RETRIES) -> bool:
        """Détermine si on doit retry"""
        return attempt < max_retries

# ============================================
# CORE: CIRCUIT BREAKER
# ============================================
class CircuitBreaker:
    """
    Pattern Circuit Breaker pour protéger contre les services défaillants
    
    States:
    - CLOSED: Normal, requests pass through
    - OPEN: Too many failures, block all requests
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self, 
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        timeout: float = CIRCUIT_BREAKER_TIMEOUT
    ):
        self.threshold = threshold
        self.timeout = timeout
        self.state = CircuitBreakerState()
    
    def record_success(self):
        """Enregistre un succès"""
        self.state.failure_count = 0
        self.state.last_success_time = time.time()
        self.state.state = CircuitState.CLOSED
    
    def record_failure(self):
        """Enregistre un échec"""
        self.state.failure_count += 1
        self.state.last_failure_time = time.time()
        
        if self.state.failure_count >= self.threshold:
            self.state.state = CircuitState.OPEN
            print(f"⚠️ Circuit breaker OPENED (failures: {self.state.failure_count})")
    
    def is_open(self) -> bool:
        """Vérifie si le circuit est ouvert"""
        if self.state.state == CircuitState.CLOSED:
            return False
        
        if self.state.state == CircuitState.OPEN:
            # Check if timeout elapsed
            if self.state.last_failure_time:
                elapsed = time.time() - self.state.last_failure_time
                if elapsed > self.timeout:
                    print("🔄 Circuit breaker entering HALF_OPEN state")
                    self.state.state = CircuitState.HALF_OPEN
                    return False
            return True
        
        # HALF_OPEN state: allow test request
        return False
    
    def get_state(self) -> str:
        """Retourne l'état actuel"""
        return self.state.state.value

# ============================================
# CORE: EVENT EMITTER (PUB/SUB)
# ============================================
class EventEmitter:
    """
    Système d'événements pub/sub pour communication découplée
    """
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.event_history: List[WebhookEvent] = []
    
    def on(self, event_type: str, callback: Callable):
        """
        S'abonne à un type d'événement
        
        Args:
            event_type: Type d'événement (ex: "order.created")
            callback: Fonction à appeler quand l'événement se produit
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        
        self.subscribers[event_type].append(callback)
        print(f"📡 Subscribed to: {event_type}")
    
    def off(self, event_type: str, callback: Callable):
        """Désabonnement"""
        if event_type in self.subscribers:
            self.subscribers[event_type].remove(callback)
    
    def emit(self, event_type: str, payload: Dict[str, Any]) -> List[Any]:
        """
        Émet un événement vers tous les subscribers
        
        Args:
            event_type: Type d'événement
            payload: Données de l'événement
            
        Returns:
            Liste des résultats des callbacks
        """
        event = WebhookEvent(
            event_type=event_type,
            payload=payload,
            timestamp=time.time()
        )
        
        # Sign the event
        event.signature = SignatureManager.sign({
            "event": event_type,
            "payload": payload,
            "timestamp": event.timestamp
        })
        
        # Store in history
        self.event_history.append(event)
        
        # Call all subscribers
        results = []
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    result = callback(event)
                    results.append(result)
                except Exception as e:
                    print(f"❌ Error in subscriber callback: {e}")
        
        return results
    
    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[WebhookEvent]:
        """Récupère l'historique des événements"""
        if event_type:
            filtered = [e for e in self.event_history if e.event_type == event_type]
            return filtered[-limit:]
        return self.event_history[-limit:]

# ============================================
# WEBHOOK CLIENT (Frontend → Backend)
# ============================================
class WebhookClient:
    """
    Client webhook pour émettre des événements vers le backend
    Utilisé côté frontend
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.circuit_breaker = CircuitBreaker()
        self.retry_handler = RetryHandler()
    
    def emit(
        self, 
        event_type: str, 
        payload: Dict[str, Any],
        retry: bool = True
    ) -> DeliveryStatus:
        """
        Émet un événement vers le backend
        
        Args:
            event_type: Type d'événement
            payload: Données
            retry: Activer les retries
            
        Returns:
            Status de la livraison
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open():
            print("⚠️ Circuit breaker is OPEN, blocking request")
            return DeliveryStatus.CIRCUIT_OPEN
        
        event = WebhookEvent(
            event_type=event_type,
            payload=payload,
            timestamp=time.time()
        )
        
        # Sign the event
        event.signature = SignatureManager.sign(event.to_dict())
        
        # Try to deliver
        attempt = 0
        while True:
            try:
                # Simulate HTTP POST (in real implementation, use requests/httpx)
                print(f"📤 Emitting event: {event_type} (attempt {attempt + 1})")
                
                # Success
                self.circuit_breaker.record_success()
                return DeliveryStatus.SUCCESS
            
            except Exception as e:
                print(f"❌ Delivery failed: {e}")
                self.circuit_breaker.record_failure()
                
                if retry and self.retry_handler.should_retry(attempt):
                    delay = self.retry_handler.calculate_backoff(attempt)
                    print(f"⏳ Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                    attempt += 1
                else:
                    return DeliveryStatus.FAILED

# ============================================
# WEBHOOK SERVER (Backend → Frontend)
# ============================================
class WebhookServer:
    """
    Serveur webhook pour gérer les événements reçus
    Utilisé côté backend
    """
    
    def __init__(self):
        self.emitter = EventEmitter()
        self.handlers: Dict[str, Callable] = {}
    
    def on(self, event_type: str):
        """
        Decorator pour enregistrer un handler
        
        Usage:
            @server.on("order.created")
            def handle_order(event):
                # Process order
                pass
        """
        def decorator(func: Callable):
            self.handlers[event_type] = func
            self.emitter.on(event_type, func)
            return func
        return decorator
    
    def handle_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite un événement reçu
        
        Args:
            event_data: Données de l'événement avec signature
            
        Returns:
            Résultat du traitement
        """
        # Extract signature
        signature = event_data.get("signature")
        if not signature:
            return {"success": False, "error": "Missing signature"}
        
        # Verify signature
        event_copy = {k: v for k, v in event_data.items() if k != "signature"}
        if not SignatureManager.verify(event_copy, signature):
            return {"success": False, "error": "Invalid signature"}
        
        # Emit event to handlers
        event_type = event_data.get("event")
        payload = event_data.get("payload", {})
        
        results = self.emitter.emit(event_type, payload)
        
        return {
            "success": True,
            "event": event_type,
            "results": results
        }

# ============================================
# UTILITY: WEBHOOK MONITOR
# ============================================
class WebhookMonitor:
    """Monitoring et statistiques des webhooks"""
    
    def __init__(self):
        self.stats = {
            "total_events": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "retries": 0,
            "circuit_breaker_trips": 0
        }
    
    def record_event(self, status: DeliveryStatus):
        """Enregistre un événement pour les stats"""
        self.stats["total_events"] += 1
        
        if status == DeliveryStatus.SUCCESS:
            self.stats["successful_deliveries"] += 1
        elif status == DeliveryStatus.FAILED:
            self.stats["failed_deliveries"] += 1
        elif status == DeliveryStatus.RETRYING:
            self.stats["retries"] += 1
        elif status == DeliveryStatus.CIRCUIT_OPEN:
            self.stats["circuit_breaker_trips"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        total = self.stats["total_events"]
        if total == 0:
            success_rate = 0
        else:
            success_rate = (self.stats["successful_deliveries"] / total) * 100
        
        return {
            **self.stats,
            "success_rate": f"{success_rate:.2f}%"
        }
    
    def print_stats(self):
        """Affiche les statistiques"""
        stats = self.get_stats()
        print("\n" + "="*50)
        print("📊 WEBHOOK STATISTICS")
        print("="*50)
        for key, value in stats.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        print("="*50 + "\n")

# ============================================
# EXEMPLE D'UTILISATION
# ============================================
if __name__ == "__main__":
    print("""
    ============================================
    🔄 WEBHOOK COMMUNICATION LAYER
    ============================================
    
    This module provides the pure essence of webhook:
    - Signature verification (HMAC-SHA256)
    - Retry logic (exponential backoff)
    - Circuit breaker (auto-protection)
    - Event emitter (pub/sub)
    
    Usage:
    ------
    # Server side (backend)
    server = WebhookServer()
    
    @server.on("order.created")
    def handle_order(event):
        print(f"Processing order: {event.payload}")
    
    # Client side (frontend)
    client = WebhookClient()
    client.emit("order.created", {"order_id": 123, "total": 99.99})
    
    ============================================
    """)
    
    # Demo
    print("🧪 Running demo...\n")
    
    # Create server
    server = WebhookServer()
    monitor = WebhookMonitor()
    
    @server.on("test.event")
    def handle_test(event):
        print(f"✅ Received: {event.event_type} - {event.payload}")
        return {"processed": True}
    
    # Create client
    client = WebhookClient()
    
    # Emit event
    status = client.emit("test.event", {"message": "Hello from webhook!"})
    monitor.record_event(status)
    
    # Process on server
    event_data = {
        "event": "test.event",
        "payload": {"message": "Hello from webhook!"},
        "timestamp": time.time(),
        "signature": SignatureManager.sign({
            "event": "test.event",
            "payload": {"message": "Hello from webhook!"},
            "timestamp": time.time()
        })
    }
    
    result = server.handle_event(event_data)
    print(f"\n📊 Result: {result}")
    
    # Show stats
    monitor.print_stats()