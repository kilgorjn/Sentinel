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
          <a href="https://github.com/kilgorjn/Sentinel/wiki" target="_blank" rel="noopener" class="nav-link github-nav-link" title="Docs">
            <svg height="18" width="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
                0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
                -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
                .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
                -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27
                .68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12
                .51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48
                0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
            </svg>
          </a>
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
  display: flex;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.github-nav-link {
  display: flex;
  align-items: center;
  padding: 8px 10px;
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
