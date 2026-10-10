import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/new" },
    {
      path: "/new",
      name: "new",
      component: () => import("../pages/new/index.vue"),
    },
    {
      path: "/jobs/:id",
      name: "job",
      component: () => import("../pages/jobs/index.vue"),
    },
    {
      path: "/history",
      name: "history",
      component: () => import("../pages/history/index.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/new" },
  ],
  scrollBehavior() {
    return { top: 0 };
  },
});
