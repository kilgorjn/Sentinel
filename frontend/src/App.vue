<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="app">
    <!-- Header Navigation -->
    <header class="app-header">
      <div class="header-left">
        <h1>Sentinel</h1>
        <nav class="nav">
          <RouterLink to="/" :class="{ active: route.path === '/' }" class="nav-link">
            Dashboard
          </RouterLink>
          <RouterLink to="/charts" :class="{ active: route.path === '/charts' }" class="nav-link">
            Charts
          </RouterLink>
          <RouterLink to="/feeds" :class="{ active: route.path === '/feeds' }" class="nav-link">
            Feeds
          </RouterLink>
        </nav>
      </div>
    </header>

    <!-- Page Content -->
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0d0d; color: #e0e0e0; font-family: system-ui, sans-serif; }

.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-header {
  background: #1a1a1a;
  border-bottom: 1px solid #222;
  padding: 16px 20px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.app-header h1 {
  font-size: 1.2rem;
  letter-spacing: 0.05em;
  color: #aaa;
  margin: 0;
  font-weight: 600;
}

.nav {
  display: flex;
  gap: 24px;
  align-items: center;
}

.nav-link {
  color: #888;
  text-decoration: none;
  font-size: 0.95rem;
  padding: 8px 12px;
  border-radius: 4px;
  transition: color 0.2s, background 0.2s;
  cursor: pointer;
}

.nav-link:hover {
  color: #e0e0e0;
  background: #222;
}

.nav-link.active {
  color: #e0e0e0;
  background: #333;
  font-weight: 600;
}

.app-main {
  flex: 1;
  padding: 0;
}
</style>
