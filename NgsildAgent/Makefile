#----------------------------------------------------------------------------------------------------------------------

IMAGE_NAME = $(IMAGE_NAME)
CONTAINER_NAME = iff-iot-agent

DEVICE_ID = ${DEVICE_ID}
GATEWAY_ID = ${GATEWAY_ID}
KEYCLOAK_URL = ${KEYCLOAK_URL}
REALM_ID = ${REALM_ID}
REALM_USER_PASSWORD = ${REALM_USER_PASSWORD}

build:
	@$(call msg,"Building iff-iot-agent ...")
	@docker build . -t ${IMAGE_NAME}

start:
	@$(call msg,"Starting iff-iot-agent container...")

	docker run  \
				-d -t -i --network=host --rm \
				--env DEVICE_ID=${DEVICE_ID} \
				--env GATEWAY_ID=${GATEWAY_ID} \
				--env KEYCLOAK_URL=${KEYCLOAK_URL}
				--env REALM_ID=${REALM_ID}
				--env REALM_USER_PASSWORD=${REALM_USER_PASSWORD}
				--name ${CONTAINER_NAME} ${IMAGE_NAME}