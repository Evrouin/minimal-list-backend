# GitHub OAuth Implementation Guide

Sign in with GitHub following the same pattern as Google OAuth.

---

## How Google OAuth Works (Reference)

1. Frontend gets an **access token** from Google (via `vue3-google-login` or Capacitor plugin)
2. Frontend sends that token to `POST /api/auth/login/google/`
3. Backend calls Google's userinfo API to verify and extract email/name/avatar
4. Backend does `get_or_create` user, issues JWT tokens, creates a session

GitHub OAuth follows the same flow with one difference: GitHub uses a **code → token exchange** (OAuth 2.0 authorization code flow) instead of a direct ID token.

---

## Flow Overview

```
Frontend → GitHub OAuth popup → gets `code`
         → POST /api/auth/login/github/ with { code }
         → Backend exchanges code for access token (GitHub API)
         → Backend fetches user info from GitHub API
         → get_or_create user → issue JWT → return tokens
```

---

## Step 1: GitHub App Setup

1. Go to **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App**
2. Set:
   - **Homepage URL:** `https://minimal-list.evrouin.com`
   - **Authorization callback URL:** `https://minimal-list.evrouin.com/auth/github/callback`
3. Copy **Client ID** and **Client Secret**

For local dev, create a second OAuth App with callback `http://localhost:3000/auth/github/callback`.

---

## Step 2: Backend

### Environment variables

```env
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
```

### View — `apps/users/views.py`

Add after `google_login`:

```python
@extend_schema(
    summary="GitHub OAuth login",
    description="Authenticate user with GitHub OAuth code. Returns JWT tokens.",
    request={
        "application/json": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "GitHub OAuth authorization code"}},
            "required": ["code"],
        }
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="10/h", method="POST")
def github_login(request):
    """Authenticate with GitHub OAuth."""
    import requests as http_requests

    code = request.data.get("code")
    if not code:
        return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Exchange code for access token
        token_resp = http_requests.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": config("GITHUB_CLIENT_ID"),
                "client_secret": config("GITHUB_CLIENT_SECRET"),
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return Response({"error": "Failed to obtain access token from GitHub"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch user info
        user_resp = http_requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        github_user = user_resp.json()

        # GitHub may not expose email publicly — fetch from emails endpoint
        email = github_user.get("email")
        if not email:
            emails_resp = http_requests.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            primary = next((e for e in emails_resp.json() if e.get("primary") and e.get("verified")), None)
            if primary:
                email = primary["email"]

        if not email:
            return Response({"error": "Email not provided by GitHub"}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        base_username = github_user.get("login", email.split("@")[0])
        username = base_username
        if User.objects.filter(username=username).exists():
            username = f"user{get_random_string(10, '0123456789')}"

        avatar_url = github_user.get("avatar_url", "")
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "first_name": (github_user.get("name") or "").split(" ")[0],
                "last_name": " ".join((github_user.get("name") or "").split(" ")[1:]),
                "avatar_url": avatar_url,
                "is_verified": True,
            },
        )

        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        else:
            updated_fields = []
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
                updated_fields.append("avatar_url")
            if not user.is_verified:
                user.is_verified = True
                user.verification_token = ""
                updated_fields.extend(["is_verified", "verification_token"])
            if updated_fields:
                user.save(update_fields=updated_fields)

        if not user.is_active:
            return Response({"error": "Your account has been deactivated."}, status=status.HTTP_403_FORBIDDEN)

        if user.locked_until and user.locked_until > timezone.now():
            return Response({"error": "Account locked. Check your email to unlock."}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        UserSession.create_from_request(user, str(refresh["jti"]), request)

        return Response({
            "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
            "user": UserSerializer(user).data,
        })

    except Exception:
        return Response({"error": "GitHub authentication failed"}, status=status.HTTP_400_BAD_REQUEST)
```

### URL — `apps/users/urls.py`

```python
# Import
from .views import ..., github_login

# Add to urlpatterns
path("login/github/", github_login, name="github_login"),
```

---

## Step 3: Frontend

### Callback page — `pages/auth/github/callback.vue`

GitHub redirects here with `?code=...` after the user authorizes.

```vue
<script setup lang="ts">
const route = useRoute()
const authStore = useAuthStore()
const api = useAuthApi()

onMounted(async () => {
  const code = route.query.code as string
  if (!code) return navigateTo('/auth/login')
  try {
    const res = await api.githubLogin(code)
    authStore.saveTokens(res.tokens)
    authStore.user = res.user
    navigateTo('/')
  } catch {
    navigateTo('/auth/login')
  }
})
</script>

<template>
  <div class="flex items-center justify-center h-screen">
    <p class="text-sm text-gray-500">Signing in with GitHub...</p>
  </div>
</template>
```

### API method — `composables/useAuthApi.ts`

```ts
githubLogin: (code: string) =>
  request<{ tokens: AuthTokens; user: User }>(`${base}/login/github/`, {
    method: 'POST',
    body: { code },
  }),
```

### Login button — `pages/auth/login.vue`

```ts
const loginWithGithub = () => {
  const clientId = useRuntimeConfig().public.githubClientId
  const redirectUri = `${window.location.origin}/auth/github/callback`
  const url = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&scope=user:email`
  window.location.href = url
}
```

```html
<button @click="loginWithGithub">Sign in with GitHub</button>
```

### Runtime config — `nuxt.config.ts`

```ts
runtimeConfig: {
  public: {
    githubClientId: process.env.NUXT_PUBLIC_GITHUB_CLIENT_ID,
  }
}
```

### `.env`

```env
NUXT_PUBLIC_GITHUB_CLIENT_ID=your_client_id
```

---

## Step 4: Middleware — allow callback route

`middleware/auth.global.ts` — add to `publicPaths`:

```ts
to.path.startsWith('/auth/github')
```

---

## Notes

- **No Capacitor plugin needed** — GitHub OAuth uses a browser redirect, not a native SDK. The callback page handles it on both web and mobile (Capacitor's browser plugin can be used for native if needed later).
- **Email scope** — `user:email` scope is requested to ensure email access even if the user's GitHub email is private.
- **Existing Google users** — if a user signs in with GitHub using the same email as an existing Google account, `get_or_create` will find the existing user and log them in (same behavior as Google).
