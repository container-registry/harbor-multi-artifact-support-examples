<script setup>
import { computed } from 'vue'

const props = defineProps(['todos', 'filter'])
defineEmits(['delete-completed'])

const remaining = computed(() => props.todos.filter((todo) => !todo.completed).length)
</script>

<template>
  <footer class="footer" v-show="todos.length > 0">
    <span class="todo-count">
      <strong>{{ remaining }}</strong> {{ remaining === 1 ? 'item' : 'items' }} left
    </span>
    <ul class="filters">
      <li><a href="#/" :class="{ selected: filter === 'all' }">All</a></li>
      <li><a href="#/active" :class="{ selected: filter === 'active' }">Active</a></li>
      <li><a href="#/completed" :class="{ selected: filter === 'completed' }">Completed</a></li>
    </ul>
    <button
      class="clear-completed"
      v-show="todos.some((todo) => todo.completed)"
      @click="$emit('delete-completed')"
    >
      Clear completed
    </button>
  </footer>
</template>
