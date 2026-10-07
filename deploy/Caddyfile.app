# Versão web do app (app.[DOMINIO]) servida pelo Caddy, com a API no mesmo endereço.
# Troque [DOMINIO] pelo seu domínio. Os arquivos vêm de:  cd mobile && npx expo export --platform web
# copiados para /srv/syncserv-web (ver README, "Versão web do app").
#
# Mesmo endereço para o site e a API: o navegador não precisa de CORS e o CSP pode ser 'self' em tudo.

app.[DOMINIO] {
	encode zstd gzip

	# API: o mesmo backend do app nativo (docker-compose.prod.yml publica em 127.0.0.1:8002)
	handle /api/* {
		reverse_proxy 127.0.0.1:8002
	}

	# App: arquivos estáticos; qualquer rota desconhecida volta para o index.html (app de página única)
	handle {
		root * /srv/syncserv-web
		try_files {path} /index.html
		file_server
	}

	header {
		Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "no-referrer"
		Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"
		Cross-Origin-Opener-Policy "same-origin"
		-Server
	}

	# Arquivos com hash no nome podem ficar em cache para sempre; o index.html nunca
	@hashed path /_expo/static/* /assets/*
	header @hashed Cache-Control "public, max-age=31536000, immutable"
	@shell path / /index.html /manifest.webmanifest
	header @shell Cache-Control "no-cache"
}
