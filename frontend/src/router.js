import { createRouter, createWebHistory } from 'vue-router'
import DashboardPage from './pages/DashboardPage.vue'
import FeedsPage from './pages/FeedsPage.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardPage,
  },
  {
    path: '/feeds',
    name: 'Feeds',
    component: FeedsPage,
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
