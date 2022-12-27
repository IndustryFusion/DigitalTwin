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

import org.keycloak.Config;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.EventListenerProviderFactory;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;



public class OispEventListenerProviderFactory
        implements EventListenerProviderFactory {
    @Override
    public final EventListenerProvider create(final KeycloakSession kcSession) {
        return new OispEventListenerProvider();
    }

    @Override
    public final void init(final Config.Scope scope) {
    }

    @Override
    public final void postInit(final KeycloakSessionFactory kcSessionFactory) {
    }

    @Override
    public final void close() {
    }

    @Override
    public final String getId() {
        return "oisp-event-listener";
    }
}
