import { createRouter, createWebHistory } from 'vue-router'
import DashboardPage from './pages/DashboardPage.vue'
import FeedsPage from './pages/FeedsPage.vue'
import ChartsPage from './pages/ChartsPage.vue'

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
  {
    path: '/charts',
    name: 'Charts',
    component: ChartsPage,
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
