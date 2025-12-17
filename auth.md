# Authentication API Documentation

This document describes all authentication-related endpoints including username/password login, OAuth (Google + GitHub), signup, account linking, and token issuance.

Base router prefix: **`/auth`**

---

# Data Models

## UserRequest (for email/password signup)

| Field        | Type     | Required | Notes |
|--------------|----------|----------|-------|
| id           | int?     | No       | Ignored on signup |
| username     | string   | Yes      | 3–30 chars; letters, numbers, `_` and `-` |
| email        | string   | Yes      | Must be unique |
| first_name   | string?  | No       |
| last_name    | string?  | No       |
| password     | string   | Yes      | Minimum length: 8 |
| phone_number | string?  | No       |

Example:
```
{
  "username": "username",
  "email": "username@gmail.com",
  "first_name": "first name",
  "last_name": "last name",
  "password": "password",
  "phone_number": "1234567890"
}
```

---

## CompleteSignupBody

Used after OAuth signup when user must pick a username.

| Field         | Type   | Required |
|---------------|--------|----------|
| pending_token | string | Yes      |
| username      | string | Yes      |

---

## BindAccountBody

Used when a user signs in with OAuth but the email already exists and must verify password to link.

| Field         | Type   |
|---------------|--------|
| pending_token | string |
| password      | string |

---

## Token (Response)

The authentication token issued after a successful sign-in.

```
{
  "access_token": "string",
  "token_type": "bearer"
}
```

---

# Authentication Flow Overview

There are three authentication modes:

---

## 1. Username + Password Login

### **POST /auth/token**

Authenticate with form data (`application/x-www-form-urlencoded`).

Form Fields:

| Field     | Type   |
|-----------|--------|
| username  | string |
| password  | string |

### Response 200
```
{
  "access_token": "jwt",
  "token_type": "bearer"
}
```

### Errors
- `401 Unauthorized` — invalid username or password.

---

## 2. Email/Password Signup (Local Account)

### **POST /auth/**

Creates a new user.

### Request Body
UserRequest schema.

### Response 201
```
"User Created"
```

### Errors
- `400 Username already taken`
- `400 E-mail already taken`

---

# OAuth Authentication (Google + GitHub)

OAuth uses **redirects**, a **pending token**, and multiple states:

- **existing user linked → issue token**
- **OAuth account belongs to another user → reject**
- **email exists but OAuth not linked → require password to bind**
- **email does not exist → require username to complete signup**

Frontend receives callback with URL parameters specifying the flow.

---

## 3. Google OAuth

### **GET /auth/google/login**

Redirects user to Google login.

### **GET /auth/google/callback**

Google returns:

- email
- provider_id (`sub`)
- profile name

Backend determines if:

1. This Google account is already linked to a local user → **login immediately**
2. Email exists but Google not linked → **require account binding**
3. New user → **require username selection**

Returned redirect URL includes parameters such as:

```
/auth/google?status=new_user&pending_token=...
```

---

## 4. GitHub OAuth

### **GET /auth/github/login**

Redirect to GitHub authorization.

### **GET /auth/github/callback**

GitHub returns:

- GitHub ID
- login (username)
- email (may require secondary `/user/emails` request)

Flow is the same as Google.

---

# Internal OAuth States

The backend sets:

```py
kind: "oauth_pending"
mode: "signup" | "link"
provider: "google" | "github"
provider_id: string
email: optional string
exp: timestamp
```


Returned to frontend via:  
`http://localhost:3000/oauth/{provider}?status=...`

---

# Post-OAuth Endpoints

## 5. Complete OAuth Signup

### **POST /auth/complete-signup**  
(Request Body: CompleteSignupBody)

Used when OAuth user has no existing account and must create one by choosing username.

### Response 200
```
{
  "access_token": "...",
  "token_type": "bearer"
}
```

### Errors
- `400 Invalid or expired token`
- `400 Username already taken`

---

## 6. Bind Existing Account to OAuth Provider

### **POST /auth/bind-account**  
(Request Body: BindAccountBody)

Used when:

- User logs in with OAuth
- Their email already exists
- Must verify password to link OAuth provider

### Response 200
```
{
  "access_token": "...",
  "token_type": "bearer"
}
```

### Errors
- `400 Invalid or expired token`
- `401 Incorrect password`
- `404 User not found`
- `400 Social account already linked`

---

# Login Logic Summary

**1. User logs in with OAuth provider**  
→ Backend identifies user or returns a `pending_token`.

**2. Pending Token "mode" determines next step:**

### `"mode": "signup"`
User must select a username → `/auth/complete-signup`

### `"mode": "link"`
User must verify password → `/auth/bind-account`

### No pending:  
User is fully authenticated → Frontend receives:

```
?status=logged_in&access_token=...
```

---

# Helper Endpoints (internal usage)

These endpoints are used indirectly in OAuth redirection flows:

---

### **GET /auth/google/login**
Starts Google OAuth.

### **GET /auth/github/login**
Starts GitHub OAuth.

### **GET /auth/google/callback**
Processes Google callback.

### **GET /auth/github/callback**
Processes GitHub callback.

These do not return JSON — they redirect to the frontend.

---

# Token Format

Issued JWT structure:

```
{
  "sub": "username",
  "id": user_id,
  "role": "user" | "admin",
  "exp": "<timestamp>"
}
```

Algorithm: **HS256**  
Expiration: **20 minutes** (local accounts), **10 minutes** (OAuth pending tokens)

---

# Protected Routes

Most other API routes require:

```
Authorization: Bearer <access_token>
```

And depend on:

```
Depends(oauth2_bearer)
```

which uses `/auth/token` by default.

---

# End of Authentication API Markdown
