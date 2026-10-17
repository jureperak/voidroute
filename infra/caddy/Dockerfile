# Caddy with the Porkbun DNS provider for DNS-01 (wildcard certificate)
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/porkbun

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
