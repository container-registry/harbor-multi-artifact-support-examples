package com.containerregistry.todo;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/todos")
@CrossOrigin(origins = "*")
public class TodoController {

    private final TodoRepository repository;

    public TodoController(TodoRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<Todo> list() {
        return repository.findAll();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Todo create(@RequestBody Todo todo) {
        todo.setId(null);
        return repository.save(todo);
    }

    @PatchMapping("/{id}")
    public Todo update(@PathVariable Long id, @RequestBody Map<String, Object> patch) {
        Todo todo = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        // A Map body is what makes this a real PATCH: an absent key must leave the field
        // untouched, which a bound Todo could not distinguish from an explicit null/false.
        if (patch.containsKey("title")) {
            todo.setTitle((String) patch.get("title"));
        }
        if (patch.containsKey("completed")) {
            todo.setCompleted(Boolean.TRUE.equals(patch.get("completed")));
        }
        return repository.save(todo);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        if (!repository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }
        repository.deleteById(id);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping(params = "completed")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteByCompleted(@RequestParam boolean completed) {
        repository.deleteByCompleted(completed);
    }
}
