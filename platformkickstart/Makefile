presubmit:
	@if ! golangci-lint version | grep $(GOLANGCI_VER); then \
		echo "Install golangci-lint $(GOLANGCI_VER)"; \
		curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $$(go env GOPATH)/bin $(GOLANGCI_VER); \
	fi
	@echo "Run golangci-lint"
	@golangci-lint run

test:
	go test ./... --timeout=10s

build:
	go build -o platformkickstart cmd/main.go

crossplane-resources:
	kubectl apply -f pkg/crossplane/deploy/definition.yaml
	kubectl apply -f pkg/crossplane/deploy/local-composition.yaml
	kubectl apply -f pkg/crossplane/deploy/ionos-composition.yaml
