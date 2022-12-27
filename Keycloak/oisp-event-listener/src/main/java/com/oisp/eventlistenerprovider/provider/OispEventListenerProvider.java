/**
 * Copyright (c) 2020 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.oisp.eventlistenerprovider.provider;

import org.keycloak.events.Event;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.admin.ResourceType;
import org.keycloak.events.admin.OperationType;
import org.keycloak.events.admin.AdminEvent;

import org.apache.http.HttpHeaders;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpDelete;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;

import java.io.IOException;

@SuppressWarnings({"javadoc"})
public class OispEventListenerProvider implements EventListenerProvider {
    private static final String USERS_PREFIX = "users/";
    private static final String USER_DELETE_ENDPOINT_ENV
        = "OISP_FRONTEND_USER_DELETE_ENDPOINT";
    private static final String OISP_FRONTEND_SECRET_ENV
        = "OISP_FRONTEND_SECRET";
    private static final String FORWARD_ADDRESS_USER_PLACEHOLDER = ":userId";

    private final String forwardAddress;
    private final String secret;
    private final CloseableHttpClient httpClient;

    public OispEventListenerProvider() {
        this.forwardAddress = System.getenv(USER_DELETE_ENDPOINT_ENV);
        this.secret = System.getenv(OISP_FRONTEND_SECRET_ENV);
        this.httpClient = HttpClients.createDefault();
    }

    @Override
    public final void onEvent(final Event event) {
    }

    @Override
    public final void onEvent(final AdminEvent adminEvent,
            final boolean includeRepresentation) {
        ResourceType rsType = adminEvent.getResourceType();
        OperationType opType = adminEvent.getOperationType();
        if (rsType != ResourceType.USER || opType != OperationType.DELETE) {
            return;
        }
        String rsPath = adminEvent.getResourcePath();
        String userId = rsPath.replace(USERS_PREFIX, "");
        System.out.println("User Deletion Occured - User ID: " + userId);
        forwardUserDeletion(userId);
    }

    private void forwardUserDeletion(final String uid) {
        String address = forwardAddress.replace(
            FORWARD_ADDRESS_USER_PLACEHOLDER, uid);
        HttpDelete req = new HttpDelete(address);
        req.addHeader(HttpHeaders.AUTHORIZATION, "Basic " + secret);
        try (CloseableHttpResponse res = httpClient.execute(req)) {
            System.out.println("Successfully forwarded user deletion: " + uid);
            res.close();
        } catch (Exception err) {
            System.out.println("Could not forward user - " + uid
                + " - deletion: " + err);
        }
    }

    @Override
    public final void close() {
        try {
            httpClient.close();
        } catch (IOException err) {
            System.out.println("Could not close Http Client "
                + " in Listener: " + err);
            System.exit(1);
        }
    }
}
