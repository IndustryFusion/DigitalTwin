<!--
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
-->

<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Fusion Frontend Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="${url.resourcesPath}/img/favicon.ico" />
    <#if properties.styles?has_content>
        <#list properties.styles?split(' ') as style>
            <link href="${url.resourcesPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.scripts?has_content>
        <#list properties.scripts?split(' ') as script>
            <script src="${url.resourcesPath}/${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
</head>
<body>
    <div class="main-container">
        <div class="content-container">
            <div class="content-area">
                <header>
                    <div>IndustryFusion</div>
                    <button>Register now!</button>
                </header>

                <div class="wrapper">
                    <form id="kc-form-login" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
                        <h1>Login</h1>
                        <p class="login">Log in now with your Fusion-ID</p>
                        <#if message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                            <div class="alert alert-${message.type}">
                                <#if message.type = 'success'><span class="pficon pficon-ok"></span></#if>
                                <#if message.type = 'warning'><span class="pficon pficon-warning-triangle-o"></span></#if>
                                <#if message.type = 'error'><span class="pficon pficon-error-circle-o"></span></#if>
                                <#if message.type = 'info'><span class="pficon pficon-info"></span></#if>
                                <span class="kc-feedback-text">${kcSanitize(message.summary)?no_esc}</span>
                            </div>
                        </#if>
                        <input type="email" name="username" placeholder="Email">
                        <input type="password" name="password" placeholder="Password">

                        <p class="forgot">Forgot your password?</p>
                        <input type="submit" name="submit" value="Login">
                        <p class="register">Register now!</p>
                    </form>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
